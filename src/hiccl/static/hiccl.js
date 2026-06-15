/**
 * Hiccl Client — WebSocket / SSE real-time sync + htmx integration.
 *
 * Transport priority:
 *   1. WebSocket  (bidirectional — actions + push)
 *   2. SSE        (unidirectional push — actions fall back to HTTP)
 *   3. HTTP only  (htmx native AJAX, no real-time push)
 */
class HicclClient {
  constructor(sessionId, wsUrl, sseUrl) {
    this.sessionId = sessionId;
    this.wsUrl = wsUrl;
    this.sseUrl = sseUrl;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.ws = null;
    this.es = null;
    this.useWS = false;
    // Active streams keyed by logical name → { channelId, callbacks, ready }.
    this.streams = new Map();
    // stream_open requests queued before the WebSocket finished opening.
    this._pendingStreamOpens = [];
    this.connect();
  }

  // ------------------------------------------------------------------
  // Connection lifecycle
  // ------------------------------------------------------------------

  connect() {
    this._tryWS();
  }

  _tryWS() {
    try {
      this.ws = new WebSocket(this.wsUrl);
    } catch (e) {
      console.warn("[hiccl] WebSocket creation failed, falling back to SSE");
      this._trySSE();
      return;
    }

    // Receive binary frames as ArrayBuffer (synchronous) rather than Blob
    // (which needs an async arrayBuffer() round-trip before we can read it).
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      console.log("[hiccl] WebSocket connected");
      this.useWS = true;
      this.reconnectDelay = 1000;
      // Flush any stream_open requests that arrived before the socket opened.
      if (this._pendingStreamOpens.length) {
        for (const payload of this._pendingStreamOpens) {
          this.ws.send(JSON.stringify(payload));
        }
        this._pendingStreamOpens = [];
      }
    };

    this.ws.onmessage = (event) => {
      // Binary frame → stream data: first byte is the channel id.
      if (event.data instanceof ArrayBuffer || event.data instanceof Blob) {
        this._handleBinary(event.data);
        return;
      }
      // Text frame → JSON control protocol.
      try {
        const msg = JSON.parse(event.data);
        this._handleMessage(msg);
      } catch (e) {
        console.error("[hiccl] WS parse error", e);
      }
    };

    this.ws.onclose = () => {
      this.useWS = false;
      console.log("[hiccl] WebSocket closed, reconnecting...");
      this._teardownAllStreams();
      setTimeout(() => this._tryWS(), this.reconnectDelay);
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay,
      );
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  _trySSE() {
    if (!this.sseUrl) {
      console.log("[hiccl] No SSE URL, using HTTP only");
      return;
    }

    try {
      this.es = new EventSource(this.sseUrl);
    } catch (e) {
      console.warn("[hiccl] SSE creation failed, using HTTP only");
      return;
    }

    this.es.addEventListener("hiccl", (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._handleMessage(msg);
      } catch (e) {
        console.error("[hiccl] SSE parse error", e);
      }
    });

    this.es.addEventListener("hiccl-stream", (event) => {
      // SSE fallback: binary stream data arrives base64-encoded.
      try {
        const payload = JSON.parse(event.data);
        if (payload.channel_id == null) return;
        this._deliverStreamData(payload.channel_id, this._decodeB64(payload.data));
      } catch (e) {
        console.error("[hiccl] stream event parse error", e);
      }
    });

    this.es.addEventListener("heartbeat", () => {
      // keepalive, no action needed
    });

    this.es.onopen = () => {
      console.log("[hiccl] SSE connected");
      this.reconnectDelay = 1000;
    };

    this.es.onerror = () => {
      console.log("[hiccl] SSE error, reconnecting...");
      // EventSource auto-reconnects, but we set a fallback
      setTimeout(() => {
        if (this.es.readyState === EventSource.CLOSED) {
          this._trySSE();
        }
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay,
      );
    };
  }

  // ------------------------------------------------------------------
  // Message handling
  // ------------------------------------------------------------------

  _handleMessage(msg) {
    switch (msg.type) {
      case "batch":
        for (const patch of msg.patches) this._applyPatch(patch);
        break;
      case "patch":
        this._applyPatch(msg);
        break;
      case "stream_ack":
        this._onStreamAck(msg);
        break;
      case "stream_close":
        this._onStreamClose(msg);
        break;
      case "error":
        console.error("[hiccl] Server error:", msg.message);
        break;
    }
  }

  _applyPatch(patch) {
    const target = document.getElementById(patch.component_id);
    if (!target) return;
    const html = patch.html;
    const swapStyle = patch.swap || "outerHTML";

    if (typeof htmx !== "undefined") {
      htmx.swap(target, html, { swapStyle });
    } else {
      if (swapStyle === "outerHTML") {
        target.outerHTML = html;
      } else {
        target.innerHTML = html;
      }
    }
  }

  // ------------------------------------------------------------------
  // Action sending (WS intercept)
  // ------------------------------------------------------------------

  sendAction(componentId, method, args = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: "action",
          component_id: componentId,
          method,
          args,
        }),
      );
      return true;
    }
    return false; // Caller should fall back to HTTP
  }

  // ------------------------------------------------------------------
  // Streams — multiplexed raw byte channels
  // ------------------------------------------------------------------

  /**
   * Open a named raw byte stream.
   *
   * @param {string} name        Logical stream name (matches server-side open_stream).
   * @param {string} componentId Owning component id (sent in stream_open).
   * @param {object} [callbacks] { onData(Uint8Array), onClose(), onError(err) }
   * @returns {StreamHandle} handle with send/close methods.
   */
  createStream(name, componentId, callbacks = {}) {
    // Allow createStream(name, callbacks) shorthand.
    if (componentId && typeof componentId === "object") {
      callbacks = componentId;
      componentId = "";
    }
    const handle = new StreamHandle(this, name, callbacks);
    if (this.streams.has(name)) {
      const existing = this.streams.get(name);
      existing._replaceCallbacks(callbacks);
    }
    this.streams.set(name, handle);

    // Ask the server to allocate a channel. The handle becomes ready on ack.
    // Buffer the request until the WebSocket is open so opens issued during
    // page load (before connect) are not silently dropped.
    this._requestStreamOpen(name, componentId);

    return handle;
  }

  _requestStreamOpen(name, componentId) {
    const payload = {
      type: "stream_open",
      stream: name,
      component_id: componentId || "",
    };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    } else {
      this._pendingStreamOpens.push(payload);
    }
  }

  _sendText(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }

  _onStreamAck(msg) {
    const handle = this.streams.get(msg.stream);
    if (!handle) return;
    handle._ack(msg.channel_id);
  }

  _onStreamClose(msg) {
    const channel_id = msg.channel_id;
    for (const [name, handle] of this.streams.entries()) {
      if (handle.channelId === channel_id) {
        handle._remoteClose();
        this.streams.delete(name);
        break;
      }
    }
  }

  _handleBinary(data) {
    // Normalise Blob → ArrayBuffer, then read the leading channel-id byte.
    if (data instanceof Blob) {
      data.arrayBuffer().then((buf) => this._dispatchBinary(new Uint8Array(buf)));
    } else {
      this._dispatchBinary(new Uint8Array(data));
    }
  }

  _dispatchBinary(bytes) {
    if (bytes.length === 0) return;
    const channelId = bytes[0];
    this._deliverStreamData(channelId, bytes.slice(1));
  }

  _deliverStreamData(channelId, data) {
    for (const handle of this.streams.values()) {
      if (handle.channelId === channelId && handle.ready) {
        handle._onData(data);
        return;
      }
    }
    // Data arrived before ack — buffer it on the first pending handle for this id.
  }

  _decodeB64(b64) {
    const bin = atob(b64 || "");
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  _teardownAllStreams() {
    for (const handle of this.streams.values()) {
      handle._remoteClose();
    }
    this.streams.clear();
  }

  disconnect() {
    this._teardownAllStreams();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (this.es) {
      this.es.close();
      this.es = null;
    }
  }
}

// ------------------------------------------------------------------
// StreamHandle — per-stream client API returned by createStream()
// ------------------------------------------------------------------

class StreamHandle {
  constructor(client, name, callbacks) {
    this.client = client;
    this.name = name;
    this.channelId = null;
    this.ready = false;
    this.closed = false;
    // Frames queued before the ack assigned a channel id.
    this._pendingSends = [];
    this._onData = callbacks.onData || (() => {});
    this._onClose = callbacks.onClose || (() => {});
    this._onError = callbacks.onError || (() => {});
  }

  _replaceCallbacks(callbacks) {
    this._onData = callbacks.onData || this._onData;
    this._onClose = callbacks.onClose || this._onClose;
    this._onError = callbacks.onError || this._onError;
  }

  _ack(channelId) {
    this.channelId = channelId;
    this.ready = true;
    // Flush any frames that arrived before the channel was assigned.
    if (this._pendingSends.length) {
      const pending = this._pendingSends;
      this._pendingSends = [];
      for (const payload of pending) this._emit(payload);
    }
  }

  _emit(payload) {
    const frame = new Uint8Array(payload.length + 1);
    frame[0] = this.channelId;
    frame.set(payload, 1);
    this.client.ws.send(frame);
  }

  _onData(data) {
    if (this.closed) return;
    this._onData(data);
  }

  _remoteClose() {
    if (this.closed) return;
    this.closed = true;
    this.ready = false;
    this._onClose();
  }

  /**
   * Send raw bytes to the server as a binary frame.
   * Falls back to HTTP POST when the WebSocket is not connected.
   * @param {Uint8Array|ArrayBuffer} data
   * @returns {boolean} true if sent over the WebSocket.
   */
  send(data) {
    if (this.closed) {
      this._onError(new Error(`stream ${this.name} is closed`));
      return false;
    }
    if (!this.client.ws || this.client.ws.readyState !== WebSocket.OPEN) {
      this._onError(new Error(`stream ${this.name} is not connected`));
      return false;
    }
    const payload = data instanceof Uint8Array ? data : new Uint8Array(data);
    // Buffer until the server has acked with a channel id (first ~1 RTT).
    if (!this.ready) {
      this._pendingSends.push(payload);
      return true;
    }
    this._emit(payload);
    return true;
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.ready = false;
    if (this.channelId != null) {
      this.client._sendText({ type: "stream_close", channel_id: this.channelId });
    }
    this.client.streams.delete(this.name);
  }
}

// ------------------------------------------------------------------
// htmx intercept: when WS is connected, route actions through WS
// ------------------------------------------------------------------

function interceptHtmxRequests(hicclClient) {
  if (typeof htmx === "undefined") return;

  document.addEventListener("htmx:configRequest", (event) => {
    if (!hicclClient.useWS) return;

    const path = event.detail.path;
    const match = path.match(/^\/hiccl\/action\/([^/]+)\/([^/]+)/);
    if (!match) return;

    const componentId = match[1];
    const method = match[2];

    // Collect parameters
    const args = {};
    if (event.detail.parameters) {
      for (const [k, v] of Object.entries(event.detail.parameters)) {
        args[k] = v;
      }
    }

    // Merge hx-vals
    const valsHeader = event.detail.headers?.["HX-vals"];
    if (valsHeader) {
      try {
        Object.assign(args, JSON.parse(valsHeader));
      } catch (e) {}
    }

    // Also try to get hx-vals from the triggering element
    const elt = event.detail.elt;
    if (elt) {
      const valsAttr = elt.getAttribute("hx-vals");
      if (valsAttr) {
        try {
          Object.assign(args, JSON.parse(valsAttr));
        } catch (e) {}
      }
    }

    // Send via WS and cancel the HTTP request
    if (hicclClient.sendAction(componentId, method, args)) {
      event.preventDefault(); // Cancel HTTP
    }
  });
}

// ------------------------------------------------------------------
// Initialization
// ------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const meta = document.querySelector('meta[name="hiccl-session"]');
  if (!meta) return;

  const sessionId = meta.getAttribute("content");
  const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProtocol}//${location.host}/hiccl/ws/${sessionId}`;
  const sseUrl = `${location.origin}/hiccl/sse/${sessionId}`;

  window.hicclClient = new HicclClient(sessionId, wsUrl, sseUrl);
  interceptHtmxRequests(window.hicclClient);
});

// Bridge htmx page transitions (hx-boost) to Alpine.js tree re-initialization
document.addEventListener("htmx:afterSettle", (event) => {
  if (typeof Alpine !== "undefined") {
    if (typeof Alpine.discover === "function") {
      Alpine.discover();
    } else if (typeof Alpine.initTree === "function") {
      const target = (event.detail && event.detail.target) || event.target || document.body;
      Alpine.initTree(target);
    }
  }
});
