import { WebSocket } from 'ws';
/** Bound socket writes by pausing reads; preserve every binary/text message. */
export function relayWebSockets(left, right, onClosed, {
  highWaterMark = 8 * 1024 * 1024,
  lowWaterMark = 4 * 1024 * 1024,
  stallTimeoutMs = 30000,
} = {}) {
  let closed = false;
  const directions = [];
  const close = () => {
    if (closed) return;
    closed = true;
    for (const direction of directions) {
      clearInterval(direction.timer);
      direction.from.off('message', direction.forward);
    }
    for (const socket of [left, right]) {
      socket.off('close', close);
      socket.off('error', close);
      socket.terminate();
    }
    onClosed?.();
  };
  for (const [from, to] of [[left, right], [right, left]]) {
    const direction = { from, to, timer: undefined, pausedAt: undefined, forward: undefined };
    const resume = () => {
      if (closed || direction.pausedAt === undefined) return;
      if (to.readyState !== WebSocket.OPEN) { close(); return; }
      if (to.bufferedAmount <= lowWaterMark) {
        clearInterval(direction.timer);
        direction.timer = undefined;
        direction.pausedAt = undefined;
        from.resume();
      } else if (performance.now() - direction.pausedAt >= stallTimeoutMs) close();
    };
    const pause = () => {
      if (closed || direction.pausedAt !== undefined) return;
      from.pause();
      direction.pausedAt = performance.now();
      direction.timer = setInterval(resume, 25);
      direction.timer.unref();
    };
    direction.forward = (data, binary) => {
      if (closed) return;
      if (to.readyState !== WebSocket.OPEN) { close(); return; }
      try {
        to.send(data, { binary }, err => { if (err) close(); else resume(); });
        if (to.bufferedAmount >= highWaterMark) pause();
      } catch { close(); }
    };
    directions.push(direction);
    from.on('message', direction.forward);
  }
  for (const socket of [left, right]) {socket.on('close', close);socket.on('error', close);}
  return close;
}
