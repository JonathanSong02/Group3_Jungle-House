// Opaque IDs only. Images stay out of textual history and escalation excerpts.
export function imageReferencesForQuestion(messages, question) {
  if (!/\b(it|its|image|photo|picture|ini|itu|dia|gambar)\b|\b(this|that|these|those)(?:\s+one)?[?!.\s]*$|它|这张|這張|这个|這個|那个|那個/i.test(question)) return [];
  const references = [];
  for (const message of [...messages].reverse()) {
    if (message.sender !== 'user') continue;
    for (const reference of message.attachment_refs || []) {
      if (/^[a-f0-9]{64}$/.test(reference) && !references.includes(reference)) references.push(reference);
    }
    if (references.length >= 4) break;
  }
  return references.slice(0, 4);
}
