"""Safe operational diagnostics: never log exception messages, file paths or SQL values."""
import secrets


def failure_response(error, logger, stage="unknown"):
    error_id = secrets.token_hex(8)
    errno = getattr(error, "errno", None)
    if errno in {1054, 1146}:
        code = "IMAGE_SCHEMA_NOT_READY"
        message = "Image storage needs a database update. Please contact a system administrator."
    elif errno in {1040, 1045, 2002, 2003, 2006, 2013, 2055}:
        code = "IMAGE_STORAGE_UNAVAILABLE"
        message = "Image storage is temporarily unavailable. Please try again later."
    else:
        code = "IMAGE_PROCESSING_FAILED"
        message = "The image request could not be completed. Please try again or contact a manager."
    logger.error("Image service failure error_id=%s code=%s stage=%s exception=%s db_errno=%s",
                 error_id, code, stage, type(error).__name__, errno)
    return {"message": message, "answer": message, "source": "image_service_unavailable",
            "code": code, "error_id": error_id, "confidence_kind": "not_calibrated",
            "answer_evidence": "not_established", "fallback": False,
            "escalation_ready": False, "escalation_required": False}
