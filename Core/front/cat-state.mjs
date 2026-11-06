// Message order and receipts are shared by the page and its boundary tests.
export function mergeMessages(previous, incoming) {
  const byId = new Map(previous.map(message => [message.id, message]));
  for (const message of incoming) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.seq - b.seq);
}
export function readPage(timeline, messages) {
  return {
    messages: mergeMessages(timeline.messages, messages),
    cursor: Math.max(timeline.cursor, ...messages.map(message => message.seq)),
  };
}
export function acceptMessage(timeline, message) {
  // A POST can overtake other writers. Only GET pages advance the read cursor.
  return {messages: mergeMessages(timeline.messages, [message]), cursor: timeline.cursor};
}
export function errorText(value) {
  return typeof value?.error === 'string' ? value.error : value?.error?.message || '未能完成请求';
}
export function sendOutcome(value) {
  if (value?.ok && value.accepted === true && value.message?.id) {
    const dispatch = {
      queued: '同桌提醒已排队',
      skipped: '本条未请求提醒',
      none: '没有其他需要提醒的参与者',
      not_configured: '提醒入口未配置',
    };
    return {state: 'saved', text: '已保存 · ' + (dispatch[value.dispatch] || '提醒结果未提供')};
  }
  const definite = value?.message_submitted === false ||
    [400, 404, 409, 422].includes(value?.status) ||
    ['cat_not_configured', 'cli_start_failed', 'empty_body', 'human_sender_only'].includes(value?.error_code);
  return definite ? {state: 'failed', text: '未发送：' + errorText(value)} :
    {state: 'unknown', text: '发送结果尚未确认。请核对原消息，暂不重发。'};
}
export function memberName(id, members) {
  if (id === 'human') return 'Human';
  const member = members.find(item => item.home_id === id);
  return member?.label || id;
}
export const seatLabels = {participant: '参与', observer: '旁听', left: '已离席'};
