/* Knox Country schematic map for the Privates tab (game X/Y, Y-down = north-up). */
(function (global) {
  const CELL = 300;

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function createKnoxMap(canvas, options) {
    const opts = options || {};
    const world = opts.world || { x0: 3000, y0: 0, x1: 16000, y1: 14000 };
    const cities = opts.cities || [];
    const map = {
      canvas,
      world,
      cities,
      houses: [],
      selected: null,
      draft: null,
      mode: "pan",
      scale: 0.04,
      vx: world.x0,
      vy: world.y0,
      dragging: false,
      drawing: false,
      lastX: 0,
      lastY: 0,
      hover: { x: 0, y: 0 },
      atlas: null,
      atlasUrl: "",
      calibration: opts.calibration || world,
      onSelect: opts.onSelect || function () {},
      onDraft: opts.onDraft || function () {},
      onHover: opts.onHover || function () {},
    };

    function cssSize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(200, Math.floor(rect.width || canvas.clientWidth || 400));
      const h = Math.max(200, Math.floor(rect.height || canvas.clientHeight || 400));
      if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
      }
      return { w, h, dpr };
    }

    function toScreen(x, y) {
      return {
        x: (x - map.vx) * map.scale,
        y: (y - map.vy) * map.scale,
      };
    }

    function toWorld(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      const { dpr } = cssSize();
      const sx = (clientX - rect.left) * dpr;
      const sy = (clientY - rect.top) * dpr;
      return {
        x: Math.floor(map.vx + sx / map.scale),
        y: Math.floor(map.vy + sy / map.scale),
      };
    }

    function fit() {
      const { w, h, dpr } = cssSize();
      const bw = world.x1 - world.x0;
      const bh = world.y1 - world.y0;
      const sx = (w * dpr) / bw;
      const sy = (h * dpr) / bh;
      map.scale = Math.max(0.008, Math.min(sx, sy) * 0.92);
      map.vx = world.x0 - ((w * dpr) / map.scale - bw) / 2;
      map.vy = world.y0 - ((h * dpr) / map.scale - bh) / 2;
      draw();
    }

    function hitHouse(wx, wy) {
      const houses = map.houses || [];
      for (let i = houses.length - 1; i >= 0; i -= 1) {
        const h = houses[i];
        const x = Number(h.x);
        const y = Number(h.y);
        const w = Number(h.w);
        const hh = Number(h.h);
        if (wx >= x && wx < x + w && wy >= y && wy < y + hh) return h;
      }
      return null;
    }

    function atlasReady() {
      const img = map.atlas;
      return !!(img && img.complete && img.naturalWidth);
    }

    function drawAtlas(ctx) {
      const img = map.atlas;
      const c = map.calibration || map.world;
      if (!atlasReady() || !c) return false;
      const worldW = Number(c.x1) - Number(c.x0);
      const worldH = Number(c.y1) - Number(c.y0);
      if (worldW <= 0 || worldH <= 0) return false;
      const pxPerX = img.naturalWidth / worldW;
      const pxPerY = img.naturalHeight / worldH;
      const sx = (map.vx - Number(c.x0)) * pxPerX;
      const sy = (map.vy - Number(c.y0)) * pxPerY;
      const sw = (canvas.width / map.scale) * pxPerX;
      const sh = (canvas.height / map.scale) * pxPerY;
      try {
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
        return true;
      } catch (err) {
        return false;
      }
    }

    function loadAtlas(info) {
      const atlas = (info && info.atlas) || info || {};
      const url = atlas.ready && atlas.url ? atlas.url : "";
      if (info && (info.x0 != null)) map.calibration = info;
      if (!url) {
        map.atlasUrl = "";
        map.atlas = null;
        draw();
        return;
      }
      if (map.atlasUrl === url && map.atlas) {
        draw();
        return;
      }
      map.atlasUrl = url;
      const img = new Image();
      img.onload = () => {
        map.atlas = img;
        draw();
      };
      img.onerror = () => {
        map.atlas = null;
        draw();
      };
      img.src = url;
    }

    function draw() {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const { w, h, dpr } = cssSize();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = (map.atlasUrl || atlasReady()) ? "#c9c4a0" : "#152016";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const painted = drawAtlas(ctx);

      const topLeft = { x: map.vx, y: map.vy };
      const botRight = {
        x: map.vx + (w * dpr) / map.scale,
        y: map.vy + (h * dpr) / map.scale,
      };

      const gridMin = painted ? 0.08 : 0.035;
      if (map.scale > gridMin) {
        ctx.strokeStyle = painted ? "rgba(40, 32, 16, 0.12)" : "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1;
        const x0 = Math.floor(topLeft.x / CELL) * CELL;
        const y0 = Math.floor(topLeft.y / CELL) * CELL;
        for (let x = x0; x <= botRight.x; x += CELL) {
          const a = toScreen(x, topLeft.y);
          const b = toScreen(x, botRight.y);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
        for (let y = y0; y <= botRight.y; y += CELL) {
          const a = toScreen(topLeft.x, y);
          const b = toScreen(botRight.x, y);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      map.cities.forEach((city) => {
        const a = toScreen(city.x1, city.y1);
        const b = toScreen(city.x2, city.y2);
        if (!painted) {
          ctx.fillStyle = "rgba(226, 135, 67, 0.12)";
          ctx.strokeStyle = "rgba(226, 135, 67, 0.45)";
          ctx.lineWidth = 1.5 * dpr;
          ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
          ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
        }
        ctx.fillStyle = painted ? "rgba(40, 28, 12, 0.88)" : "rgba(242, 243, 245, 0.85)";
        ctx.font = `${11 * dpr}px Inter, system-ui, sans-serif`;
        ctx.fillText(city.name || city.id, a.x + 6 * dpr, a.y + 16 * dpr);
      });

      (map.houses || []).forEach((house) => {
        const a = toScreen(Number(house.x), Number(house.y));
        const bw = Number(house.w) * map.scale;
        const bh = Number(house.h) * map.scale;
        const selected = map.selected && house.x === map.selected.x && house.y === map.selected.y
          && house.w === map.selected.w && house.h === map.selected.h;
        ctx.fillStyle = selected ? "rgba(88, 166, 255, 0.35)" : "rgba(63, 185, 80, 0.28)";
        ctx.strokeStyle = selected ? "#58a6ff" : "#3fb950";
        ctx.lineWidth = (selected ? 2.5 : 1.5) * dpr;
        ctx.fillRect(a.x, a.y, bw, bh);
        ctx.strokeRect(a.x, a.y, bw, bh);
        if (map.scale > 0.05) {
          ctx.fillStyle = painted ? "rgba(40, 28, 12, 0.92)" : "#f2f3f5";
          ctx.font = `${10 * dpr}px Inter, system-ui, sans-serif`;
          ctx.fillText(String(house.title || house.owner || ""), a.x + 4 * dpr, a.y + 12 * dpr);
        }
      });

      if (map.draft) {
        const d = map.draft;
        const x = Math.min(d.x1, d.x2);
        const y = Math.min(d.y1, d.y2);
        const dw = Math.abs(d.x2 - d.x1) + 1;
        const dh = Math.abs(d.y2 - d.y1) + 1;
        const a = toScreen(x, y);
        ctx.setLineDash([6 * dpr, 4 * dpr]);
        ctx.strokeStyle = d.overlap ? "#f85149" : "#E28743";
        ctx.fillStyle = d.overlap ? "rgba(248, 81, 73, 0.22)" : "rgba(226, 135, 67, 0.22)";
        ctx.lineWidth = 2 * dpr;
        ctx.fillRect(a.x, a.y, dw * map.scale, dh * map.scale);
        ctx.strokeRect(a.x, a.y, dw * map.scale, dh * map.scale);
        ctx.setLineDash([]);
      }
    }

    function setHouses(houses) {
      map.houses = houses || [];
      draw();
    }

    function setSelected(house) {
      map.selected = house || null;
      draw();
    }

    function setMode(mode) {
      map.mode = mode === "draw" ? "draw" : "pan";
      canvas.style.cursor = map.mode === "draw" ? "crosshair" : "grab";
    }

    function setDraft(draft) {
      map.draft = draft;
      draw();
    }

    canvas.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      const pos = toWorld(ev.clientX, ev.clientY);
      map.lastX = ev.clientX;
      map.lastY = ev.clientY;
      if (map.mode === "draw") {
        map.drawing = true;
        map.draft = { x1: pos.x, y1: pos.y, x2: pos.x, y2: pos.y, overlap: false };
        map.onDraft(map.draft);
        draw();
        return;
      }
      const hit = hitHouse(pos.x, pos.y);
      if (hit) {
        map.selected = hit;
        map.onSelect(hit);
        draw();
        return;
      }
      map.dragging = true;
      canvas.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (ev) => {
      const pos = toWorld(ev.clientX, ev.clientY);
      map.hover = pos;
      map.onHover(pos);
      if (map.drawing && map.draft) {
        map.draft.x2 = pos.x;
        map.draft.y2 = pos.y;
        map.onDraft(map.draft);
        draw();
        return;
      }
      if (!map.dragging) return;
      const { dpr } = cssSize();
      const dx = (ev.clientX - map.lastX) * dpr;
      const dy = (ev.clientY - map.lastY) * dpr;
      map.lastX = ev.clientX;
      map.lastY = ev.clientY;
      map.vx -= dx / map.scale;
      map.vy -= dy / map.scale;
      draw();
    });

    window.addEventListener("mouseup", () => {
      if (map.drawing && map.draft) {
        map.drawing = false;
        map.onDraft(map.draft, true);
      }
      map.dragging = false;
      if (map.mode === "pan") canvas.style.cursor = "grab";
    });

    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const { dpr } = cssSize();
      const pos = toWorld(ev.clientX, ev.clientY);
      const factor = ev.deltaY > 0 ? 0.9 : 1.1;
      const next = clamp(map.scale * factor, 0.01, 2.0);
      const rect = canvas.getBoundingClientRect();
      const sx = (ev.clientX - rect.left) * dpr;
      const sy = (ev.clientY - rect.top) * dpr;
      map.vx = pos.x - sx / next;
      map.vy = pos.y - sy / next;
      map.scale = next;
      draw();
    }, { passive: false });

    window.addEventListener("resize", () => draw());
    setMode("pan");
    if (opts.calibration || (opts.atlas && opts.atlas.url)) {
      loadAtlas(opts.calibration || opts);
    }
    fit();

    return {
      fit,
      draw,
      setHouses,
      setSelected,
      setMode,
      setDraft,
      setAtlas: loadAtlas,
      toWorld,
      getDraftRect() {
        if (!map.draft) return null;
        const x = Math.min(map.draft.x1, map.draft.x2);
        const y = Math.min(map.draft.y1, map.draft.y2);
        return {
          x,
          y,
          w: Math.abs(map.draft.x2 - map.draft.x1) + 1,
          h: Math.abs(map.draft.y2 - map.draft.y1) + 1,
          overlap: !!map.draft.overlap,
        };
      },
      markOverlap(flag) {
        if (map.draft) map.draft.overlap = !!flag;
        draw();
      },
      clearDraft() {
        map.draft = null;
        draw();
      },
    };
  }

  global.MeatballsPrivatesMap = { createKnoxMap };
})(window);
