(function () {
  "use strict";

  function slugify(str) {
    return str.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((k) => {
        if (k === "text") node.textContent = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  function formatTime(seconds) {
    if (!isFinite(seconds) || seconds < 0) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  }

  const TRACK_ICON = '<svg class="track-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';

  // --- Shared player -------------------------------------------------

  const Player = (function () {
    const audio = document.getElementById("player-audio");
    const bar = document.getElementById("player-bar");
    const toggleBtn = document.getElementById("player-toggle");
    const iconPlay = document.getElementById("icon-play");
    const iconPause = document.getElementById("icon-pause");
    const titleEl = document.getElementById("player-title");
    const seekEl = document.getElementById("player-seek");
    const currentEl = document.getElementById("player-current");
    const durationEl = document.getElementById("player-duration");

    let activeBtn = null;
    let activePlaylist = null; // array of {url, btn} for auto-advance
    let activeIndex = -1;
    let seeking = false;

    function setPlayingIcon(isPlaying) {
      iconPlay.hidden = isPlaying;
      iconPause.hidden = !isPlaying;
      toggleBtn.setAttribute("aria-label", isPlaying ? "Pause" : "Play");
    }

    function clearActive() {
      if (activeBtn) activeBtn.classList.remove("playing");
      activeBtn = null;
    }

    function playItem(url, label, btn, playlist, index) {
      if (activeBtn === btn) {
        // same track: just toggle
        togglePlayPause();
        return;
      }
      clearActive();
      activeBtn = btn;
      activePlaylist = playlist;
      activeIndex = index;
      activeBtn.classList.add("playing");

      bar.hidden = false;
      titleEl.textContent = label;
      audio.src = url;
      audio.currentTime = 0;
      audio.play();
    }

    function togglePlayPause() {
      if (!audio.src) return;
      if (audio.paused) audio.play();
      else audio.pause();
    }

    function playNext() {
      if (!activePlaylist || activeIndex < 0) return;
      for (let i = activeIndex + 1; i < activePlaylist.length; i++) {
        const next = activePlaylist[i];
        if (next.url) {
          playItem(next.url, next.label, next.btn, activePlaylist, i);
          return;
        }
      }
      clearActive();
      setPlayingIcon(false);
    }

    toggleBtn.addEventListener("click", togglePlayPause);
    audio.addEventListener("play", () => setPlayingIcon(true));
    audio.addEventListener("pause", () => setPlayingIcon(false));
    audio.addEventListener("ended", playNext);
    audio.addEventListener("loadedmetadata", () => {
      durationEl.textContent = formatTime(audio.duration);
    });
    audio.addEventListener("timeupdate", () => {
      if (seeking) return;
      currentEl.textContent = formatTime(audio.currentTime);
      if (audio.duration) {
        seekEl.value = String(Math.round((audio.currentTime / audio.duration) * 1000));
      }
    });
    seekEl.addEventListener("input", () => {
      seeking = true;
      currentEl.textContent = formatTime((seekEl.value / 1000) * (audio.duration || 0));
    });
    seekEl.addEventListener("change", () => {
      if (audio.duration) audio.currentTime = (seekEl.value / 1000) * audio.duration;
      seeking = false;
    });

    return { playItem };
  })();

  // --- Video modal -------------------------------------------------

  const VideoModal = (function () {
    const modal = document.getElementById("video-modal");
    const backdrop = document.getElementById("video-modal-backdrop");
    const closeBtn = document.getElementById("video-modal-close");
    const titleEl = document.getElementById("video-modal-title");
    const player = document.getElementById("video-modal-player");

    function open(url, label) {
      titleEl.textContent = label;
      player.src = url;
      modal.hidden = false;
      player.play();
    }

    function close() {
      player.pause();
      player.removeAttribute("src");
      player.load();
      modal.hidden = true;
    }

    closeBtn.addEventListener("click", close);
    backdrop.addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !modal.hidden) close();
    });

    return { open };
  })();

  const VIDEO_ICON = '<svg class="track-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11z"/></svg>';

  // --- Rendering -------------------------------------------------

  function buildUnitJump(units, catalogId) {
    const nav = el("nav", { class: "unit-jump" });
    units.forEach((u) => {
      const a = el("a", { href: `#${catalogId}-${slugify(u.unit)}`, text: u.unit });
      nav.appendChild(a);
    });
    return nav;
  }

  function buildTrackList(items, links, missingCounter) {
    const list = el("ul", { class: "track-list" });
    const playlist = []; // parallel to items, for auto-advance within this unit

    items.forEach((item, index) => {
      const url = links[item.filename];
      const li = el("li");

      if (url) {
        const btn = el("button", { type: "button", class: "track" });
        btn.innerHTML = TRACK_ICON;
        btn.appendChild(document.createTextNode(item.label));
        btn.addEventListener("click", () => Player.playItem(url, item.label, btn, playlist, index));
        li.appendChild(btn);
        playlist.push({ url, label: item.label, btn });
      } else {
        missingCounter.count++;
        playlist.push({ url: null, label: item.label, btn: null });
        li.appendChild(el("span", {
          class: "track missing",
          title: "Audio not uploaded yet",
          text: item.label + " (not yet available)"
        }));
      }
      list.appendChild(li);
    });

    return list;
  }

  function buildCatalogBlock(levelId, catalog, links, missingCounter) {
    const catalogId = `${levelId}-${slugify(catalog.catalog)}`;
    const block = el("section", { class: "catalog-block" });
    block.appendChild(el("h2", { text: catalog.catalog }));
    block.appendChild(buildUnitJump(catalog.units, catalogId));

    catalog.units.forEach((u) => {
      const section = el("section", { class: "unit-section", id: `${catalogId}-${slugify(u.unit)}` });
      section.appendChild(el("h3", { text: u.unit }));
      section.appendChild(buildTrackList(u.items, links, missingCounter));
      block.appendChild(section);
    });

    const top = el("div", { class: "top-link" });
    top.appendChild(el("a", { href: "#top", text: "Back to top" }));
    block.appendChild(top);

    return block;
  }

  function buildVideoTrackList(items, links, missingCounter) {
    const list = el("ul", { class: "track-list" });
    items.forEach((item) => {
      const url = links[item.filename];
      const li = el("li");
      if (url) {
        const btn = el("button", { type: "button", class: "track video" });
        btn.innerHTML = VIDEO_ICON;
        btn.appendChild(document.createTextNode(item.label));
        btn.addEventListener("click", () => VideoModal.open(url, item.label));
        li.appendChild(btn);
      } else {
        missingCounter.count++;
        li.appendChild(el("span", {
          class: "track missing",
          title: "Video not uploaded yet",
          text: item.label + " (not yet available)"
        }));
      }
      list.appendChild(li);
    });
    return list;
  }

  function buildVideoBlock(levelId, videoLevel, links, missingCounter) {
    const catalogId = `${levelId}-grammar-videos`;
    const block = el("section", { class: "catalog-block" });
    block.appendChild(el("h2", { text: "Grammar Videos" }));
    block.appendChild(buildUnitJump(videoLevel.units, catalogId));

    videoLevel.units.forEach((u) => {
      const section = el("section", { class: "unit-section", id: `${catalogId}-${slugify(u.unit)}` });
      section.appendChild(el("h3", { text: u.unit }));
      section.appendChild(buildVideoTrackList(u.items, links, missingCounter));
      block.appendChild(section);
    });

    const top = el("div", { class: "top-link" });
    top.appendChild(el("a", { href: "#top", text: "Back to top" }));
    block.appendChild(top);

    return block;
  }

  function buildLevelPanel(level, links, missingCounter, videoLevel) {
    const levelId = slugify(level.level);
    const panel = el("div", { class: "level-panel", id: `panel-${levelId}` });
    level.catalogs.forEach((catalog) => {
      panel.appendChild(buildCatalogBlock(levelId, catalog, links, missingCounter));
    });
    if (videoLevel) {
      panel.appendChild(buildVideoBlock(levelId, videoLevel, links, missingCounter));
    }
    return panel;
  }

  function activateLevel(levelId) {
    document.querySelectorAll(".level-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `panel-${levelId}`);
    });
    document.querySelectorAll(".level-tabs button").forEach((b) => {
      b.classList.toggle("active", b.dataset.level === levelId);
    });
  }

  function render(catalogData, links, videoCatalogData) {
    const tabsEl = document.getElementById("level-tabs");
    const panelsEl = document.getElementById("level-panels");
    const missingCounter = { count: 0 };

    catalogData.forEach((level, i) => {
      const levelId = slugify(level.level);
      const videoLevel = videoCatalogData.find((v) => v.level === level.level);
      const btn = el("button", { type: "button", "data-level": levelId, text: level.level });
      btn.addEventListener("click", () => activateLevel(levelId));
      tabsEl.appendChild(btn);
      panelsEl.appendChild(buildLevelPanel(level, links, missingCounter, videoLevel));
      if (i === 0) activateLevel(levelId);
    });

    const total = countAll(catalogData) + countAll(videoCatalogData, true);
    if (missingCounter.count > 0) {
      const banner = el("div", {
        class: "status-banner",
        text: `${missingCounter.count} of ${total} tracks are not yet hosted. They'll appear automatically once added to data/links.json.`
      });
      panelsEl.parentNode.insertBefore(banner, panelsEl);
    }
  }

  function countAll(catalogData, isVideo) {
    let total = 0;
    if (isVideo) {
      catalogData.forEach((l) => l.units.forEach((u) => { total += u.items.length; }));
    } else {
      catalogData.forEach((l) => l.catalogs.forEach((c) => c.units.forEach((u) => { total += u.items.length; })));
    }
    return total;
  }

  Promise.all([
    fetch("data/catalog.json").then((r) => r.json()),
    fetch("data/links.json").then((r) => r.json()).catch(() => ({})),
    fetch("data/video_catalog.json").then((r) => (r.ok ? r.json() : [])).catch(() => [])
  ]).then(([catalogData, links, videoCatalogData]) => {
    render(catalogData, links, videoCatalogData);
  }).catch((err) => {
    document.getElementById("level-panels").textContent = "Failed to load catalog: " + err;
  });
})();
