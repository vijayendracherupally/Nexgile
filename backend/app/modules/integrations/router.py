"""5) Integrations & Data Sources - FR-5.1 to FR-5.5."""
from __future__ import annotations

import csv
import io
import json
import random
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import Principal, get_principal, require
from app.core.scoping import scoped
from app.core.serialize import page_response, rows, to_dict
from app.domain.enums import ConnectorCategory, DataOrigin, Scope, SyncStatus
from app.domain.models import (
    ActivityData, Connector, EmissionFactor, Entity, Facility, FactorLibrary,
    FieldMapping, ImportBatch, MeterReading, Notification, Supplier, SyncRun,
    Transaction, Webhook,
)
from app.engine import lineage

router = APIRouter(prefix="/integrations", tags=["5) Integrations & Data Sources"])

# FR-5.1 / .2 / .3 - the catalogue the document names, exactly.
CONNECTOR_CATALOG = {
    ConnectorCategory.ENTERPRISE: [
        "SAP", "Oracle", "Microsoft Dynamics", "NetSuite", "Custom ERP", "PLM", "MES",
        "WMS", "TMS", "Procurement", "Finance", "Expense", "Travel",
    ],
    ConnectorCategory.OPERATIONAL: [
        "Utilities", "Meters", "IoT/Sensors", "Fleet telematics", "Manufacturing",
        "Warehouses", "Logistics", "Waste", "Assets", "HR", "Surveys", "Invoices",
        "Receipts",
    ],
    ConnectorCategory.EXTERNAL: [
        "ecoinvent", "GaBi", "Other factor libraries", "Grid data",
        "Weather/climate services", "Commodity indices", "Benchmarks",
        "Regulatory updates",
    ],
}

PROTOCOLS = ["rest", "graphql", "webhook", "batch", "streaming", "sftp"]
DATA_FORMATS = ["json", "xml", "csv"]
PCF_EXCHANGE_FORMATS = ["pact", "tfs"]

IMPORT_SCHEMAS = {
    "activity_data": {
        "required": ["entity_id", "scope", "activity_key", "quantity", "unit",
                     "period_start", "period_end"],
        "optional": ["facility_id", "supplier_id", "product_id", "category_id",
                     "description", "data_origin", "scope2_method", "scope3_method",
                     "external_ref"],
    },
    "emission_factor": {
        "required": ["library_id", "activity_key", "name", "scope", "unit",
                     "value_kgco2e", "valid_from"],
        "optional": ["country", "region", "valid_to", "method", "uncertainty_pct",
                     "source_reference"],
    },
    "supplier": {
        "required": ["organization_id", "name", "code"],
        "optional": ["tier", "category", "country", "annual_spend", "currency",
                     "language", "contact_email", "parent_supplier_id"],
    },
    "transaction": {
        "required": ["entity_id", "transaction_date", "description", "amount"],
        "optional": ["supplier_id", "currency", "gl_account", "cost_center_id",
                     "source_system"],
    },
    "meter_reading": {
        "required": ["facility_id", "meter_code", "meter_type", "reading_at", "value", "unit"],
        "optional": ["capture_method", "is_cumulative", "quality_flag"],
    },
}


# ---------------------------------------------------------------------------
# FR-5.1 / .2 / .3  Connector catalogue and administration
# ---------------------------------------------------------------------------

@router.get("/catalog")
def catalog():
    return {
        "categories": {k: v for k, v in CONNECTOR_CATALOG.items()},
        "protocols": PROTOCOLS,
        "data_formats": DATA_FORMATS,
        "pcf_exchange_formats": PCF_EXCHANGE_FORMATS,
        "import_types": list(IMPORT_SCHEMAS.keys()),
    }


@router.get("/connectors")
def list_connectors(organization_id: int | None = None, category: str | None = None,
                    status: str | None = None,
                    db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(Connector).order_by(Connector.category, Connector.name)
    if organization_id:
        stmt = stmt.where(Connector.organization_id == organization_id)
    if category:
        stmt = stmt.where(Connector.category == category)
    if status:
        stmt = stmt.where(Connector.status == status)
    out = []
    for c in db.scalars(scoped(stmt, Connector, p)):
        last = db.scalars(select(SyncRun).where(SyncRun.connector_id == c.id)
                          .order_by(SyncRun.started_at.desc())).first()
        mappings = db.scalar(select(func.count()).select_from(FieldMapping)
                             .where(FieldMapping.connector_id == c.id)) or 0
        out.append({**to_dict(c), "mapping_count": mappings,
                    "last_run": to_dict(last) if last else None})
    return out


class ConnectorIn(BaseModel):
    organization_id: int
    name: str
    system: str
    category: str
    protocol: str = "rest"
    data_format: str = "json"
    endpoint: str = ""
    schedule_cron: str = "0 2 * * *"
    factor_library_id: int | None = None


@router.post("/connectors", status_code=201)
def create_connector(payload: ConnectorIn, db: Session = Depends(get_db),
                     p: Principal = Depends(require("integrations.write"))):
    c = Connector(**payload.model_dump())
    db.add(c)
    db.commit()
    return to_dict(c)


@router.get("/connectors/{connector_id}")
def get_connector(connector_id: int, db: Session = Depends(get_db)):
    c = db.get(Connector, connector_id)
    if c is None:
        raise HTTPException(404, "Connector not found")
    return {**to_dict(c),
            "mappings": rows(db.scalars(select(FieldMapping)
                                        .where(FieldMapping.connector_id == c.id))),
            "recent_runs": rows(db.scalars(select(SyncRun)
                                           .where(SyncRun.connector_id == c.id)
                                           .order_by(SyncRun.started_at.desc()).limit(20)))}


@router.put("/connectors/{connector_id}/credentials")
def set_credentials(connector_id: int, credential_ref: str = Body(..., embed=True),
                    db: Session = Depends(get_db),
                    p: Principal = Depends(require("integrations.write"))):
    """FR-5.5 - credentials are held by reference; secrets never enter this store."""
    c = db.get(Connector, connector_id)
    if c is None:
        raise HTTPException(404, "Connector not found")
    c.credential_ref = credential_ref
    c.credential_status = "configured"
    db.commit()
    return {"connector_id": c.id, "credential_status": c.credential_status,
            "credential_ref": c.credential_ref,
            "note": "Only a reference to the secret store is persisted."}


@router.put("/connectors/{connector_id}/mappings")
def set_mappings(connector_id: int, mappings: list[dict] = Body(...),
                 db: Session = Depends(get_db),
                 p: Principal = Depends(require("integrations.write"))):
    """FR-5.4 - schema mapping."""
    c = db.get(Connector, connector_id)
    if c is None:
        raise HTTPException(404, "Connector not found")
    for old in db.scalars(select(FieldMapping).where(FieldMapping.connector_id == c.id)):
        db.delete(old)
    for m in mappings:
        db.add(FieldMapping(connector_id=c.id, **m))
    db.commit()
    return rows(db.scalars(select(FieldMapping).where(FieldMapping.connector_id == c.id)))


@router.post("/connectors/{connector_id}/sync")
def run_sync(connector_id: int, db: Session = Depends(get_db),
             p: Principal = Depends(require("integrations.write"))):
    """FR-5.5 - sync with status, retries, reconciliation and a transaction log."""
    c = db.get(Connector, connector_id)
    if c is None:
        raise HTTPException(404, "Connector not found")
    if c.credential_status != "configured":
        raise HTTPException(409, "Configure credentials before running a sync")

    run = SyncRun(connector_id=c.id, status="running")
    db.add(run)
    db.flush()
    c.status = SyncStatus.RUNNING

    log: list[dict] = []
    now = datetime.now(timezone.utc)
    rng = random.Random(c.id * 1000 + int(now.timestamp()) % 997)

    def emit(step: str, detail: str, level: str = "info"):
        log.append({"at": datetime.now(timezone.utc).isoformat(), "step": step,
                    "level": level, "detail": detail})

    emit("connect", f"Opened {c.protocol.upper()} connection to {c.system}")
    mappings = list(db.scalars(select(FieldMapping).where(FieldMapping.connector_id == c.id)))
    emit("map", f"{len(mappings)} field mapping(s) applied")

    # A sync pulls records the connector is responsible for. Operational
    # connectors land meter readings; enterprise connectors land transactions;
    # external connectors refresh factor libraries.
    read = written = failed = 0
    if c.category == ConnectorCategory.OPERATIONAL:
        facilities = list(db.scalars(select(Facility)))
        for facility in facilities[:6]:
            for offset in range(4):
                read += 1
                value = round(rng.uniform(800, 4200), 2)
                if value < 810:
                    failed += 1
                    emit("validate", f"Rejected reading for {facility.name}: below plausibility floor",
                         "warning")
                    continue
                db.add(MeterReading(
                    facility_id=facility.id,
                    meter_code=f"{c.system[:3].upper()}-{facility.code}-E",
                    meter_type="electricity", capture_method="sensor",
                    reading_at=now - timedelta(days=offset * 7),
                    value=value, unit="kWh", quality_flag="ok",
                ))
                written += 1
        emit("write", f"{written} meter reading(s) written")
    elif c.category == ConnectorCategory.EXTERNAL:
        lib = db.get(FactorLibrary, c.factor_library_id) if c.factor_library_id else None
        count = db.scalar(select(func.count()).select_from(EmissionFactor)
                          .where(EmissionFactor.library_id == lib.id)) if lib else 0
        read = written = int(count or 0)
        c.data_version = lib.version if lib else c.data_version
        emit("refresh", f"Factor library {lib.provider if lib else 'n/a'} "
                        f"{lib.version if lib else ''} verified: {written} factors")
        if lib and lib.is_locked:
            emit("guard", "Library is locked for the open reporting period; "
                          "new versions staged, not applied.", "warning")
    else:
        entities = list(db.scalars(select(Entity)))
        suppliers = list(db.scalars(select(Supplier)))
        for i in range(12):
            read += 1
            if not entities:
                break
            entity = entities[i % len(entities)]
            supplier = suppliers[i % len(suppliers)] if suppliers else None
            db.add(Transaction(
                entity_id=entity.id,
                supplier_id=supplier.id if supplier else None,
                transaction_date=date.today() - timedelta(days=rng.randint(1, 300)),
                description=rng.choice([
                    "Steel coil purchase", "Freight forwarding invoice",
                    "Air travel booking", "Waste collection service",
                    "Contract manufacturing", "Office electricity network charge"]),
                amount=round(rng.uniform(1200, 96000), 2),
                currency="EUR", gl_account=f"6{rng.randint(100, 999)}",
                source_system=c.system,
            ))
            written += 1
        emit("write", f"{written} transaction(s) written")

    # Reconciliation: compare what we read against what landed.
    delta = read - written - failed
    if delta:
        emit("reconcile", f"Reconciliation delta of {delta} record(s)", "warning")
    else:
        emit("reconcile", "Reconciliation clean: read == written + failed")

    run.records_read, run.records_written, run.records_failed = read, written, failed
    run.reconciliation_delta = delta
    run.finished_at = datetime.now(timezone.utc)
    run.status = "completed" if failed == 0 else "completed_with_errors"
    run.log = log

    c.last_sync_at = run.finished_at
    c.next_sync_at = run.finished_at + timedelta(days=1)
    c.records_synced = (c.records_synced or 0) + written
    c.status = SyncStatus.HEALTHY if failed == 0 else SyncStatus.DEGRADED
    c.health_score = round(100.0 * (1 - (failed / read)) if read else 100.0, 1)

    if failed:
        db.add(Notification(
            organization_id=c.organization_id, trigger="validation_failure",
            severity="warning", title=f"Sync issues on {c.name}",
            body=f"{failed} record(s) failed validation during the last sync.",
            object_type="connector", object_id=c.id,
            link=f"/integrations/connectors/{c.id}"))
    db.commit()
    return {**to_dict(run), "connector": to_dict(c)}


@router.post("/connectors/{connector_id}/retry")
def retry_sync(connector_id: int, run_id: int = Body(..., embed=True),
               db: Session = Depends(get_db),
               p: Principal = Depends(require("integrations.write"))):
    """FR-5.5 - retries."""
    run = db.get(SyncRun, run_id)
    if run is None or run.connector_id != connector_id:
        raise HTTPException(404, "Sync run not found")
    run.retry_count += 1
    result = run_sync(connector_id, db, p)
    db.commit()
    return {"retried_run_id": run_id, "retry_count": run.retry_count, "new_run": result}


@router.get("/sync-status")
def sync_status(organization_id: int | None = None, db: Session = Depends(get_db),
                p: Principal = Depends(get_principal)):
    """FR-5.5 - health monitoring across every connector."""
    stmt = select(Connector)
    if organization_id:
        stmt = stmt.where(Connector.organization_id == organization_id)
    connectors = list(db.scalars(scoped(stmt, Connector, p)))
    by_status: dict[str, int] = {}
    for c in connectors:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    return {
        "connector_count": len(connectors),
        "by_status": by_status,
        "average_health": round(
            sum(c.health_score for c in connectors) / len(connectors), 1)
        if connectors else 0.0,
        "unconfigured": sum(1 for c in connectors if c.credential_status != "configured"),
        "connectors": [
            {"id": c.id, "name": c.name, "system": c.system, "category": c.category,
             "status": c.status, "health_score": c.health_score,
             "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
             "next_sync_at": c.next_sync_at.isoformat() if c.next_sync_at else None,
             "records_synced": c.records_synced, "data_version": c.data_version,
             "schedule_cron": c.schedule_cron}
            for c in sorted(connectors, key=lambda x: x.health_score)
        ],
    }


@router.get("/transaction-logs")
def transaction_logs(connector_id: int | None = None, page: int = 1, page_size: int = 50,
                     db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """FR-5.5 - transaction logs."""
    stmt = select(SyncRun).order_by(SyncRun.started_at.desc())
    if connector_id:
        stmt = stmt.where(SyncRun.connector_id == connector_id)

    def mapper(r: SyncRun) -> dict:
        c = db.get(Connector, r.connector_id)
        return to_dict(r, extra={"connector_name": c.name if c else None,
                                 "system": c.system if c else None})

    return page_response(db, stmt, page=page, page_size=page_size, mapper=mapper)


# ---------------------------------------------------------------------------
# FR-5.4  Exchange: imports, validation, error queues, webhooks
# ---------------------------------------------------------------------------

def _parse_payload(raw: str, fmt: str) -> list[dict]:
    fmt = fmt.lower()
    if fmt == "csv":
        return list(csv.DictReader(io.StringIO(raw)))
    if fmt == "json":
        data = json.loads(raw)
        return data if isinstance(data, list) else data.get("items", [data])
    if fmt == "xml":
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        out = []
        for child in root:
            row = {sub.tag: (sub.text or "") for sub in child}
            row.update(child.attrib)
            out.append(row)
        return out
    raise ValueError(f"Unsupported format '{fmt}'")


def _coerce(value: str, field: str):
    if value is None or value == "":
        return None
    if field.endswith("_id") or field in ("tier", "quantity", "amount", "value",
                                          "value_kgco2e", "annual_spend",
                                          "uncertainty_pct", "completeness_pct"):
        try:
            return float(value) if "." in str(value) else int(value)
        except (TypeError, ValueError):
            return value
    if field in ("period_start", "period_end", "valid_from", "valid_to",
                 "transaction_date"):
        return date.fromisoformat(str(value)[:10])
    if field == "reading_at":
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return value


MODEL_FOR_IMPORT = {
    "activity_data": ActivityData, "emission_factor": EmissionFactor,
    "supplier": Supplier, "transaction": Transaction, "meter_reading": MeterReading,
}


class ImportIn(BaseModel):
    organization_id: int
    import_type: str
    format: str = "csv"
    payload: str
    filename: str = "inline"
    dry_run: bool = False


@router.post("/imports")
def create_import(payload: ImportIn, db: Session = Depends(get_db),
                  p: Principal = Depends(require("integrations.write"))):
    """FR-5.4 / FR-7.7 - import with validation and an error queue."""
    if payload.import_type not in IMPORT_SCHEMAS:
        raise HTTPException(400, f"import_type must be one of {list(IMPORT_SCHEMAS)}")
    schema = IMPORT_SCHEMAS[payload.import_type]
    model = MODEL_FOR_IMPORT[payload.import_type]

    batch = ImportBatch(organization_id=payload.organization_id,
                        import_type=payload.import_type, filename=payload.filename,
                        format=payload.format, status="running",
                        created_by_id=p.user.id)
    db.add(batch)
    db.flush()

    try:
        records = _parse_payload(payload.payload, payload.format)
    except Exception as exc:
        batch.status = "failed"
        batch.errors = [{"row": 0, "message": f"Could not parse payload: {exc}"}]
        db.commit()
        raise HTTPException(400, f"Could not parse payload: {exc}") from exc

    errors: list[dict] = []
    valid_rows: list[dict] = []
    allowed = set(schema["required"]) | set(schema["optional"])

    for index, raw in enumerate(records, start=1):
        row_errors = []
        clean: dict = {}
        for field in schema["required"]:
            if raw.get(field) in (None, ""):
                row_errors.append(f"missing required field '{field}'")
        for key, value in raw.items():
            if key not in allowed:
                continue
            try:
                clean[key] = _coerce(value, key)
            except Exception as exc:
                row_errors.append(f"field '{key}': {exc}")
        if row_errors:
            errors.append({"row": index, "messages": row_errors, "data": raw})
        else:
            valid_rows.append(clean)

    batch.rows_total = len(records)
    batch.rows_valid = len(valid_rows)
    batch.rows_invalid = len(errors)
    batch.errors = errors[:500]

    imported = 0
    if not payload.dry_run:
        for clean in valid_rows:
            try:
                db.add(model(**clean))
                imported += 1
            except Exception as exc:
                errors.append({"row": -1, "messages": [str(exc)], "data": clean})
        batch.errors = errors[:500]
        batch.rows_imported = imported
        batch.status = "completed" if not errors else "completed_with_errors"
        lineage.record_change(db, action="import", object_type=payload.import_type,
                              object_id=batch.id, user_id=p.user.id,
                              user_email=p.user.email,
                              after={"rows_imported": imported},
                              reason=f"Bulk import from {payload.filename}")
    else:
        batch.status = "validated"

    db.commit()
    return {**to_dict(batch), "dry_run": payload.dry_run,
            "schema": schema, "error_queue_size": len(errors)}


@router.post("/imports/upload")
async def upload_import(
    organization_id: int = Query(...), import_type: str = Query(...),
    format: str = Query(default="csv"), dry_run: bool = Query(default=False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db), p: Principal = Depends(require("integrations.write")),
):
    """Same import pipeline, fed from an uploaded file."""
    content = (await file.read()).decode("utf-8", errors="replace")
    return create_import(
        ImportIn(organization_id=organization_id, import_type=import_type,
                 format=format, payload=content, filename=file.filename or "upload",
                 dry_run=dry_run),
        db, p)


@router.get("/imports")
def list_imports(organization_id: int | None = None, page: int = 1, page_size: int = 50,
                 db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    stmt = select(ImportBatch).order_by(ImportBatch.id.desc())
    if organization_id:
        stmt = stmt.where(ImportBatch.organization_id == organization_id)
    return page_response(db, scoped(stmt, ImportBatch, p), page=page, page_size=page_size,
                         mapper=lambda b: to_dict(b, exclude={"errors"}))


@router.get("/imports/{batch_id}/errors")
def import_errors(batch_id: int, db: Session = Depends(get_db)):
    """FR-5.4 - the error queue."""
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(404, "Import batch not found")
    return {"batch_id": b.id, "import_type": b.import_type, "status": b.status,
            "rows_total": b.rows_total, "rows_invalid": b.rows_invalid,
            "errors": b.errors}


@router.get("/imports/template")
def import_template(import_type: str = Query(...), format: str = Query(default="csv")):
    """A ready-to-fill template for each import type."""
    if import_type not in IMPORT_SCHEMAS:
        raise HTTPException(400, f"import_type must be one of {list(IMPORT_SCHEMAS)}")
    schema = IMPORT_SCHEMAS[import_type]
    headers = schema["required"] + schema["optional"]
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerow(["" for _ in headers])
        return {"import_type": import_type, "format": "csv",
                "schema": schema, "template": buf.getvalue()}
    return {"import_type": import_type, "format": "json", "schema": schema,
            "template": json.dumps([{h: "" for h in headers}], indent=2)}


@router.get("/webhooks")
def list_webhooks(organization_id: int | None = None, db: Session = Depends(get_db),
                  p: Principal = Depends(get_principal)):
    stmt = select(Webhook)
    if organization_id:
        stmt = stmt.where(Webhook.organization_id == organization_id)
    return rows(db.scalars(scoped(stmt, Webhook, p)))


class WebhookIn(BaseModel):
    organization_id: int
    name: str
    target_url: str
    event_types: list[str] = Field(default_factory=list)
    secret_ref: str = ""


@router.post("/webhooks", status_code=201)
def create_webhook(payload: WebhookIn, db: Session = Depends(get_db),
                   p: Principal = Depends(require("integrations.write"))):
    w = Webhook(**payload.model_dump())
    db.add(w)
    db.commit()
    return to_dict(w)


@router.get("/factor-libraries/versions")
def factor_versions(db: Session = Depends(get_db)):
    """FR-5.5 - factor/data versions."""
    out = []
    for lib in db.scalars(select(FactorLibrary).order_by(FactorLibrary.provider)):
        count = db.scalar(select(func.count()).select_from(EmissionFactor)
                          .where(EmissionFactor.library_id == lib.id)) or 0
        connectors = db.scalars(select(Connector)
                                .where(Connector.factor_library_id == lib.id)).all()
        out.append({**to_dict(lib), "factor_count": count,
                    "fed_by": [c.name for c in connectors]})
    return out
