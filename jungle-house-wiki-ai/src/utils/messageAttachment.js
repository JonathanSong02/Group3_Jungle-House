export const MESSAGE_FILE_ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.heic,.heif,.pdf,.doc,.docx';

export function messagePayload(data, file) {
  if (!file) return data;
  const payload = new FormData();
  Object.entries(data).forEach(([key, value]) => {
    if (value != null) payload.append(key, value);
  });
  payload.append('attachment', file);
  return payload;
}

export function pastedImage(event, select) {
  const item = Array.from(event.clipboardData?.items || [])
    .find((entry) => entry.type.startsWith('image/'));
  const file = item?.getAsFile();
  if (file) {
    event.preventDefault();
    select(file);
  }
}

export function validateMessageFile(file) {
  return file && /\.(png|jpe?g|gif|webp|heic|heif|pdf|docx?)$/i.test(file.name)
    && file.size > 0 && file.size <= 7 * 1024 * 1024;
}
