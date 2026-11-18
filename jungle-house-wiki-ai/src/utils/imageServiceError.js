// Operational image failures are not AI answers and have no confidence percentage.
export function imageFailureDetails(error, imageRequest) {
  if (!imageRequest) return {};
  const payload = error?.response?.data || {};
  const source = ['image_service_unavailable', 'attachment_unavailable'].includes(payload.source)
    ? payload.source : 'frontend_request_error';
  return {
    error: true,
    fallback: false,
    confidence_kind: 'not_calibrated',
    answer_evidence: 'not_established',
    source,
    error_code: /^[A-Z_]{3,64}$/.test(payload.code || '') ? payload.code : undefined,
    error_id: /^[a-f0-9]{16}$/.test(payload.error_id || '') ? payload.error_id : undefined,
  };
}
