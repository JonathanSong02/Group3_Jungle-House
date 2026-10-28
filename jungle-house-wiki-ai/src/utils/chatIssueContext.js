// Browser excerpts are contextual evidence supplied by the staff member,
// never an independently verified server transcript or approved policy.
const STOP = new Set(('the and its this that what how about for with you your are can should where when ' +
  'have does from into please answer question opening closing open close correction actually mean ' +
  'dia itu kalau apa saya yang untuk kedai buka tutup at in is do to of a an price benefits benefit shelf life ' +
  'long days time know need tell help store keep put locked lock').split(' '));

function text(value) {
  return String(value || '').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ')
    .replace(/(?:data:|blob:)[^\s]+/gi, '').replace(/\s+/g, ' ').trim();
}

function tokens(value) {
  const normalized = text(value).toLowerCase();
  const result = new Set((normalized.match(/[a-z0-9]+/g) || [])
    .filter((word) => word.length > 2 && !STOP.has(word)));
  for (const run of normalized.match(/[\u3400-\u9fff]+/g) || []) {
    for (let i = 0; i < run.length - 1; i += 1) result.add(run.slice(i, i + 2));
  }
  return result;
}

function attachments(message) {
  const values = [...(Array.isArray(message.image_files) ? message.image_files : []), message.attachment_url, message.image_url];
  return [...new Set(values.filter((value) => typeof value === 'string').map((value) => {
    // Historical absolute URLs are reduced to private paths, never fetched here.
    const match = value.match(/(?:^|https?:\/\/[^/]+)(\/static\/uploads\/chat\/[A-Za-z0-9_.-]+)$/);
    return match?.[1];
  }).filter(Boolean))].slice(0, 4);
}

function readable(message) {
  const body = message.sender === 'user' ? message.text : (message.answer || message.text || message.reply);
  const steps = message.type === 'sop' && Array.isArray(message.steps)
    ? message.steps.map((step) => `Step ${step.step_number}: ${step.content || ''}`).join('\n') : '';
  return text([body, steps].filter(Boolean).join('\n'));
}

function inheritsTopic(value) {
  return /^(?:its\b|it\b|and\s+(?:its|benefits)\b|(?:how|what) about (?:it|opening|closing)[?.!\s]*$|correction\b|actually\b|i mean\b|not this\b|next\b|step\s*\d|khasiat dia|kalau buka kedai[?.!\s]*$|maksud saya|sebenarnya)|那[它牠]|^那(?:开店|開店)[呢吗嗎？?\s]*$|^(?:更正|纠正|糾正|其实|其實|我是说|我是說)/i.test(value);
}

function rejectsAnswer(value) {
  return /not what i (?:want|mean)|not this\b|wrong answer|this is wrong|none of these|^(?:(?:this|that|your answer) is )?not correct[.!?\s]*$|不是我要|^(?:不对|不對|答错|答錯)[。！!？?\s]*$|(?:回答|答案).*(?:不对|不對|错|錯)|bukan jawapan|jawapan.*(?:salah|bukan)|^tak betul[.!?\s]*$/i.test(value);
}

export function getClarificationToken(messages, issueContext) {
  if (!issueContext) return '';
  return messages.findLast((message) => message.clarification_token && message.clarification_issue_id === issueContext.issue_id)?.clarification_token || '';
}

export function buildIssueContext(messages, triggerQuestion, conversationId, offerId = null) {
  const turns = [];
  for (const message of messages) {
    if (!message || !['user', 'ai'].includes(message.sender)) continue;
    if (message.sender === 'user') turns.push({ user: message, messages: [] });
    const turn = turns.at(-1);
    if (!turn || message.loading || /^frontend_/.test(message.source || '') || message.source === 'user_stopped_generation') continue;
    const content = readable(message);
    const files = attachments(message);
    if (!content && !files.length) continue;
    turn.messages.push({ id: String(message.id), role: message.sender === 'user' ? 'user' : 'assistant',
      content: content.slice(0, 2000), timestamp: message.created_at || null,
      attachments: files, truncated: content.length > 2000 });
  }
  const clusters = [];
  for (const turn of turns) {
    const userTokens = tokens(turn.user.text);
    let chosen = null;
    let best = 0;
    let tied = false;
    const rejection = rejectsAnswer(String(turn.user.text || ''));
    if (rejection) chosen = turns[turns.indexOf(turn) - 1]?.cluster;
    for (const cluster of rejection ? [] : clusters) {
      const score = [...userTokens].reduce((sum, word) => sum + (cluster.userTokens.has(word) ? 3 : cluster.allTokens.has(word) ? 1 : 0), 0);
      if (score > best) { best = score; chosen = cluster; tied = false; }
      else if (score > 0 && score === best) tied = true;
    }
    if (tied) chosen = null;
    const question = String(turn.user.text || '');
    const operationalTransition = /^(?:(?:how|what) about (?:opening|closing)[?.!\s]*|kalau (?:buka|tutup) kedai[?.!\s]*|那(?:开店|開店|关店|關店|打烊)[呢吗嗎？?\s]*)$/i.test(question);
    if (!chosen && operationalTransition) {
      const operational = clusters.filter((cluster) => cluster.turns.some((item) => /\b(?:opening|closing|kiosk)\b|(?:buka|tutup) kedai|开店|開店|打烊|关店|關店/i.test(item.user.text)));
      if (operational.length === 1) chosen = operational[0];
    } else if (!chosen && inheritsTopic(question)) {
      chosen = turns[turns.indexOf(turn) - 1]?.cluster;
    }
    if (!chosen) {
      chosen = { id: String(turn.user.id), userTokens: new Set(), allTokens: new Set(), turns: [] };
      clusters.push(chosen);
    }
    turn.cluster = chosen;
    chosen.turns.push(turn);
    userTokens.forEach((word) => chosen.userTokens.add(word));
    tokens(turn.messages.map((item) => item.content).join(' ')).forEach((word) => chosen.allTokens.add(word));
  }
  let target = null;
  if (offerId != null) target = turns.find((turn) => turn.messages.some((item) => item.id === String(offerId)));
  if (!target) target = turns.findLast((turn) => text(turn.user.text) === text(triggerQuestion));
  if (!target?.cluster) return null;
  const selected = target.cluster.turns.flatMap((turn) => turn.messages);
  const indices = new Set();
  let chars = 0;
  // Preserve the beginning as well as the latest clarification. A short
  // preview must not lose the staff's original question on a long issue.
  const priority = [...selected.slice(0, 2).map((_, index) => index), ...selected.map((_, index) => index).reverse()];
  for (const index of priority) {
    if (indices.has(index) || indices.size >= 40 || chars + selected[index].content.length > 40000) continue;
    indices.add(index);
    chars += selected[index].content.length;
  }
  const kept = [...indices].sort((a, b) => a - b).map((index) => selected[index]);
  const first = target.cluster.turns[0].messages.find((item) => item.role === 'user')?.content || '';
  const correction = target.cluster.turns.findLast((turn) => /^(?:correction\b|actually\b|i mean\b|maksud saya|sebenarnya|更正|纠正|糾正|其实|其實|我是说|我是說)/i.test(turn.user.text))?.user.text;
  const description = [...new Set([first, correction, text(triggerQuestion)].filter(Boolean))].map((item) => text(item).slice(0, 320)).join('\n');
  return { version: 1, conversation_id: conversationId, issue_id: target.cluster.id,
    description: description || text(triggerQuestion).slice(0, 500),
    messages: kept, omitted_messages: selected.length - kept.length };
}
