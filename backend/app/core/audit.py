"""
Audit Logging Utility for Security-Relevant Access Events

Provides structured audit logging for sensitive operations:
- Student data access
- Report generation/access
- Session access/management
- Admin actions
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.models import AuditLog, User

# Configure logger
logger = logging.getLogger("edusense.audit")
logger.setLevel(logging.INFO)

# File handler for persistent audit logs
import os
from pathlib import Path
_log_dir = Path(__file__).parent.parent.parent / "logs" / "audit"
_log_dir.mkdir(parents=True, exist_ok=True)

_file_handler = logging.FileHandler(_log_dir / "audit.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON lines
logger.addHandler(_file_handler)
logger.propagate = False


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", "unknown")


def log_audit_event(
    db: Session,
    action: str,
    user: Optional[User] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """
    Log a security-relevant audit event to both database and file.

    Args:
        db: Database session
        action: Action performed (e.g., "read_student_data", "generate_report")
        user: User who performed the action (None for anonymous/system)
        resource_type: Type of resource accessed (e.g., "session", "report", "student")
        resource_id: ID of the resource accessed
        details: Additional context as dictionary
        request: FastAPI Request object for IP/user-agent extraction

    Returns:
        The created AuditLog entry
    """
    ip_address = get_client_ip(request) if request else None
    user_agent = get_user_agent(request) if request else None

    audit_entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=json.dumps(details) if details else None,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    # Also log to file for SIEM integration
    log_data = {
        "timestamp": audit_entry.created_at.isoformat(),
        "audit_id": audit_entry.id,
        "user_id": audit_entry.user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    logger.info(json.dumps(log_data, ensure_ascii=False))

    return audit_entry


# Convenience functions for common audit events

def log_student_data_access(
    db: Session,
    user: User,
    target_student_id: int,
    action: str = "read_student_data",
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Log access to student personal/academic data."""
    return log_audit_event(
        db=db,
        action=action,
        user=user,
        resource_type="student",
        resource_id=str(target_student_id),
        details=details,
        request=request,
    )


def log_report_access(
    db: Session,
    user: User,
    report_id: int,
    action: str = "read_report",
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Log access to session reports."""
    return log_audit_event(
        db=db,
        action=action,
        user=user,
        resource_type="report",
        resource_id=str(report_id),
        details=details,
        request=request,
    )


def log_session_access(
    db: Session,
    user: User,
    session_id: int,
    action: str = "access_session",
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Log session access (view, join, leave, etc.)."""
    return log_audit_event(
        db=db,
        action=action,
        user=user,
        resource_type="session",
        resource_id=str(session_id),
        details=details,
        request=request,
    )


def log_admin_action(
    db: Session,
    user: User,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Log administrative actions."""
    return log_audit_event(
        db=db,
        action=action,
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        request=request,
    )


def log_auth_event(
    db: Session,
    action: str,  # login_success, login_failed, logout, password_reset, etc.
    user: Optional[User] = None,
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Log authentication-related events."""
    return log_audit_event(
        db=db,
        action=f"auth_{action}",
        user=user,
        resource_type="auth",
        resource_id=None,
        details=details,
        request=request,
    )