    const $ = (id) => document.getElementById(id);
    function track(eventName, _props) {
      if (window.goatcounter && typeof window.goatcounter.count === 'function') {
        window.goatcounter.count({ path: eventName, event: true });
      }
    }
    const fmtEuro = (n) => `${Number(n).toFixed(2)} €`;
    const fmtKm = (n) => `${Number(n).toFixed(2)} km`;
    const fmtPrice = (n) => `${Number(n).toFixed(3)} €/L`;
    const fmtLiters = (n) => `${Number(n).toFixed(2)} L`;
    const parsePositiveDecimal = (id) => {
      const value = Number($(id).value.replace(',', '.'));
      return Number.isFinite(value) && value > 0 ? value : null;
    };
    let refreshMessageTimer = null;
    let lastCatalogRefreshValue = null;
    let lastCatalogStatus = null;
    let catalogStatusPoller = null;
    function formatRefreshDate(value) {
      if (!value) return '--';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '--';
      const time = new Intl.DateTimeFormat('es-ES', {
        hour: 'numeric',
        minute: '2-digit',
      }).format(date);
      const day = new Intl.DateTimeFormat('es-ES', {
        day: '2-digit',
        month: '2-digit',
      }).format(date);
      return `${time} ${day}`;
    }

    function refreshTimestampValue(catalog) {
      return (
        catalog?.source_fetched_at
        || catalog?.catalog?.source_fetched_at
        || catalog?.source_fetch_completed_at
        || catalog?.catalog?.source_fetch_completed_at
        || catalog?.built_at
        || catalog?.catalog?.built_at
        || ''
      );
    }

    function refreshTimestamp(catalog) {
      return formatCatalogDate(refreshTimestampValue(catalog), { includeTime: true });
    }

    function catalogValue(catalog, key) {
      return catalog?.[key] ?? catalog?.catalog?.[key] ?? '';
    }

    function formatCatalogDate(value, { includeTime = false } = {}) {
      if (!value) return '--';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '--';
      const dateText = new Intl.DateTimeFormat('es-ES', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }).format(date);
      if (!includeTime) return dateText;
      const timeText = new Intl.DateTimeFormat('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
      return `${dateText} ${timeText}`;
    }

    function catalogReasons(catalog) {
      const raw = catalogValue(catalog, 'degraded_reasons');
      if (Array.isArray(raw)) return raw.filter(Boolean).map(String);
      if (typeof raw === 'string' && raw.trim()) {
        try {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) return parsed.filter(Boolean).map(String);
        } catch (_) {
          return [raw];
        }
      }
      return [];
    }

    function summarizeCatalogReason(reason) {
      const text = String(reason || '').trim();
      if (!text) return '';
      if (/MINETUR fetch failed|Could not fetch MINETUR/i.test(text)) {
        return 'No se pudo refrescar MINETUR; usando datos locales.';
      }
      if (/PRICE_CACHE/i.test(text)) return 'Usando caché de precios con metadatos limitados.';
      if (/BALLENOIL_CACHE/i.test(text)) return 'Usando caché parcial de Ballenoil.';
      return text.length > 120 ? `${text.slice(0, 117)}...` : text;
    }

    function sourceLabel(catalog) {
      const source = String(catalogValue(catalog, 'source') || '').trim();
      if (!source) return 'Fuente: --';
      if (/SNAPSHOT/i.test(source)) return 'Datos de snapshot';
      if (/PRICE_CACHE/i.test(source)) return 'Datos de caché de precios';
      if (/BALLENOIL_CACHE/i.test(source)) return 'Datos parciales Ballenoil';
      return `Fuente: ${source}`;
    }

    function isCatalogDegraded(catalog) {
      const degraded = catalogValue(catalog, 'degraded');
      return degraded === true || degraded === 'true' || catalogReasons(catalog).length > 0;
    }

    function catalogFreshnessClass(value) {
      const date = new Date(value || '');
      if (Number.isNaN(date.getTime())) return 'freshness-unknown';
      const now = new Date();
      const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const startOfStampDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      if (startOfStampDay.getTime() === startOfToday.getTime()) return 'freshness-fresh';
      const ageMs = now.getTime() - date.getTime();
      const weekMs = 7 * 24 * 60 * 60 * 1000;
      return ageMs >= 0 && ageMs <= weekMs ? 'freshness-recent' : 'freshness-stale';
    }

    function updateCatalogDetails(catalog) {
      if (!catalog) return;
      const dot = $('catalog_freshness_dot');
      if (dot) {
        dot.classList.remove('freshness-unknown', 'freshness-fresh', 'freshness-recent', 'freshness-stale');
        dot.classList.add(catalogFreshnessClass(refreshTimestampValue(catalog)));
      }
    }

    function updateRefreshLabel(catalog, mode = 'default') {
      const stamp = refreshTimestamp(catalog);
      const rawStamp = refreshTimestampValue(catalog);
      if (rawStamp) {
        lastCatalogRefreshValue = rawStamp;
      }
      updateCatalogDetails(catalog);
      clearTimeout(refreshMessageTimer);
      $('refresh_status').textContent = `Precios actualizados: ${stamp}`;
    }

    async function loadCatalogStatus({ announceChange = false } = {}) {
      const previousStamp = lastCatalogRefreshValue;
      const response = await fetch('/catalog/status');
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo leer el catálogo');
      lastCatalogStatus = data;
      const currentStamp = refreshTimestampValue(data);
      const hasNewRefresh = Boolean(announceChange && previousStamp && currentStamp && currentStamp !== previousStamp);
      updateRefreshLabel(data, hasNewRefresh ? 'success' : 'default');
      if (hasNewRefresh) {
        await loadOptions();
      }
      return data;
    }

    function startCatalogStatusPolling() {
      if (catalogStatusPoller) return;
      catalogStatusPoller = window.setInterval(() => {
        loadCatalogStatus({ announceChange: true }).catch(() => {});
      }, 30000);
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
      }[char]));
    }

    function renderSuggestion(item, idx) {
      const title = escapeHtml(item.title || item.name || item.label);
      const type = escapeHtml(item.layer_label || 'Lugar');
      const subtitle = escapeHtml(item.subtitle || item.label);
      return `
        <button class="suggestion" type="button" data-idx="${idx}">
          <span class="suggestion-title">
            <span>${title}</span>
            <span class="suggestion-type">${type}</span>
          </span>
          <span class="suggestion-subtitle">${subtitle}</span>
        </button>
      `;
    }

    function selectedBrands() {
      return [...document.querySelectorAll('[name="brand_filter"]:checked')].map(input => input.value);
    }

    function excludedBrands() {
      return brandInputs().filter(input => !input.checked).map(input => input.value);
    }

    function brandInputs() {
      return [...document.querySelectorAll('[name="brand_filter"]')];
    }

    function allBrandsSelected() {
      const inputs = brandInputs();
      return inputs.length > 0 && inputs.every(input => input.checked);
    }

    function shouldUseBrandExclusions(selected, excluded) {
      return excluded.length > 0 && selected.length > 10;
    }

    function updateBrandFilterState() {
      const allSelected = allBrandsSelected();
      const excludedCount = excludedBrands().length;
      if (allSelected) {
        state.brandFilterMode = 'all';
      }
      const allExcept = state.brandFilterMode === 'all_except' && excludedCount > 0;
      $('select_all_brands').classList.toggle('active', allSelected || allExcept);
      $('select_all_brands').setAttribute('aria-pressed', allExcept ? 'mixed' : String(allSelected));
      $('select_all_brands').textContent = allExcept ? `Todas excepto ${excludedCount}` : 'Todas';
    }

    const BRAND_LOGOS = {
      'REPSOL':    '/static/logos/repsol.png',
      'CEPSA':     '/static/logos/cepsa.png',
      'GALP':      '/static/logos/galp.png',
      'BALLENOIL': '/static/logos/ballenoil.png',
      'PLENERGY':  '/static/logos/plenergy.png',
      'PLENOIL':   '/static/logos/plenergy.png',
      'BP':        '/static/logos/bp.png',
      'SHELL':     '/static/logos/shell.png',
      'Q8':        '/static/logos/q8.svg',
      'AVIA':      '/static/logos/avia.svg',
      'DISA':      '/static/logos/disa.svg',
      'CARREFOUR': '/static/logos/carrefour.svg',
      'EROSKI':    '/static/logos/eroski.svg',
      'ALCAMPO':   '/static/logos/alcampo.png',
      'ENI':       '/static/logos/eni.svg',
      'TAMOIL':    '/static/logos/tamoil.svg',
      'MEROIL':    '/static/logos/meroil.jpg',
      'AGLA':      '/static/logos/agla.jpg',
      'PETROPRIX': '/static/logos/petroprix.png',
      'PETROCAT':  '/static/logos/petrocat.jpg',
      'PETROCAT DIRECTE': '/static/logos/petrocat.jpg',
      'BEROIL':    '/static/logos/beroil.jpg',
      'GASEXPRESS': '/static/logos/gasexpress.jpg',
      'HAM':       '/static/logos/ham.png',
      'BONAREA':   '/static/logos/bonarea.svg',
      'ESCLAT':    '/static/logos/esclat.png',
      'ESCLATOIL': '/static/logos/esclat.png',
      'VALCARCE':  '/static/logos/valcarce.svg',
    };
    const BRAND_LOGO_FALLBACK = '/static/logos/generic-station.svg';

    function brandLogoFor(brand) {
      if (!brand) return BRAND_LOGO_FALLBACK;
      const canonical = (typeof brand === 'string') ? brand : (brand.canonical || '');
      return BRAND_LOGOS[canonical] || BRAND_LOGO_FALLBACK;
    }

    function renderBrands(brands) {
      const realBrands = brands.filter(brand => !brand.is_virtual);
      const virtualBrands = brands.filter(brand => brand.is_virtual);
      const visible = [...realBrands.slice(0, 24), ...virtualBrands];
      $('brand_checks').innerHTML = visible.map((brand) => {
        const logoSrc = brandLogoFor(brand);
        const hasSpecificLogo = Boolean(BRAND_LOGOS[brand.canonical]);
        const logoClass = hasSpecificLogo ? 'brand-logo' : 'brand-logo brand-logo--generic';
        const logoAlt = brand.is_virtual
          ? 'Gasolinera sin marca reconocida'
          : `Logo ${escapeHtml(brand.label)}`;
        return `
        <label class="brand-check${brand.is_virtual ? ' brand-check--virtual' : ''}" title="${escapeHtml(brand.label)}">
          <span class="brand-logo-frame" aria-hidden="true">
            <img class="${logoClass}" src="${logoSrc}" alt="${logoAlt}" loading="lazy" onerror="this.src='${BRAND_LOGO_FALLBACK}';this.className='brand-logo brand-logo--generic'">
          </span>
          <span class="brand-copy">
            <strong>${escapeHtml(brand.label)}</strong>
            <small>${Number(brand.station_count || 0).toLocaleString('es-ES')} estaciones</small>
            ${brand.hint ? `<small class="brand-hint">${escapeHtml(brand.hint)}<\/small>` : ''}
          </span>
          <input type="checkbox" name="brand_filter" value="${escapeHtml(brand.canonical)}" checked>
          <span class="brand-toggle" aria-hidden="true"></span>
        </label>`;
      }).join('');
      updateBrandFilterState();
    }

    const state = {
      active: 'origin',
      inputMode: 'liters',
      origin: null,
      destination: null,
      markers: {},
      route: null,
      routeKey: '',
      routeRequestId: 0,
      lastOptimization: null,
      selectedResultIndex: 0,
      selectedStation: null,
      focusRequestId: 0,
      reverseGeocodeRequestId: 0,
      alternativesOpen: false,
      resultHasFit: false,
      sidebarCollapsed: false,
      brandFilterMode: 'all',
      userLocationMarker: null,
      userLocationAccuracyCircle: null,
    };

    const map = L.map('map', { zoomControl: false, doubleClickZoom: false }).setView([40.4168, -3.7038], 6);
    L.control.zoom({ position: 'bottomleft' }).addTo(map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);
    map.createPane('routePane');
    map.getPane('routePane').style.zIndex = '450';
    map.createPane('selectedStationPane');
    map.getPane('selectedStationPane').style.zIndex = '650';
    map.createPane('userLocationPane');
    map.getPane('userLocationPane').style.zIndex = '640';

    const icons = {
      origin: L.divIcon({ className: '', html: '<div style="width:18px;height:18px;border-radius:50%;background:#171411;border:3px solid #fbf8f1;box-shadow:0 4px 16px rgba(0,0,0,.32)"></div>', iconSize: [18,18], iconAnchor: [9,9] }),
      destination: L.divIcon({ className: '', html: '<div style="width:18px;height:18px;border-radius:50%;background:#9f7a3a;border:3px solid #fbf8f1;box-shadow:0 4px 16px rgba(0,0,0,.32)"></div>', iconSize: [18,18], iconAnchor: [9,9] }),
      station: L.divIcon({ className: 'station-pin-icon', html: '<div class="station-pin"></div>', iconSize: [34,44], iconAnchor: [17,42], popupAnchor: [0,-38] }),
    };

    const desktopSidebarQuery = window.matchMedia('(min-width: 1001px)');
    const LOW_LOCATION_ACCURACY_M = 1000;
    const USER_LOCATION_ZOOM_BOOST = 2;
    const USER_LOCATION_MIN_ZOOM = 16;
    let mapResizeTimer = null;

    function refreshMapSize() {
      setTimeout(() => {
        map.invalidateSize({ pan: false });
        if (state.route || (state.origin && state.selectedStation && state.destination)) {
          fitRouteToUsableViewport(null);
        }
      }, 340);
    }

    function setSidebarCollapsed(collapsed) {
      state.sidebarCollapsed = false;
      refreshMapSize();
    }

    function mapCenterForStation(station) {
      const target = L.latLng(station.lat, station.lon);
      const mapRect = $('map').getBoundingClientRect();
      const result = $('result');
      const resultVisible = result && result.getAttribute('data-empty') !== 'true';
      let offsetX = 0;
      if (resultVisible && desktopSidebarQuery.matches) {
        const resultRect = result.getBoundingClientRect();
        const panelLeft = Math.max(0, resultRect.left - mapRect.left - 24);
        if (panelLeft > mapRect.width * .45) {
          const usableCenterX = panelLeft / 2;
          offsetX = usableCenterX - mapRect.width / 2;
        }
      }
      const zoom = map.getZoom();
      const targetPoint = map.project(target, zoom);
      return map.unproject(targetPoint.subtract(L.point(offsetX, 0)), zoom);
    }

    function focusStation(station, animate = true) {
      map.panTo(mapCenterForStation(station), {
        animate,
        duration: .45,
        easeLinearity: .25,
      });
    }

    function scheduleStationFocus(station, delayMs = 0) {
      state.focusRequestId += 1;
      const requestId = state.focusRequestId;
      setTimeout(() => {
        if (requestId !== state.focusRequestId) return;
        focusStation(station, true);
      }, delayMs);
    }

    function setRouteStatus(message = '', tone = '') {
      const element = $('route_status');
      element.textContent = message;
      element.classList.toggle('visible', Boolean(message));
      element.classList.toggle('error', tone === 'error');
    }

    function userLocationErrorMessage(error) {
      if (!navigator.geolocation) return 'Tu navegador no soporta geolocalización.';
      if (!error) return 'No se pudo obtener tu ubicación.';
      if (error.code === error.PERMISSION_DENIED) return 'Permiso de ubicación denegado.';
      if (error.code === error.POSITION_UNAVAILABLE) return 'Ubicación no disponible.';
      if (error.code === error.TIMEOUT) return 'La ubicación ha tardado demasiado.';
      return 'No se pudo obtener tu ubicación.';
    }

    function userLocationTargetZoom() {
      const maxZoom = typeof map.getMaxZoom === 'function' ? map.getMaxZoom() : 19;
      return Math.min(maxZoom, Math.max(map.getZoom() + USER_LOCATION_ZOOM_BOOST, USER_LOCATION_MIN_ZOOM));
    }

    function renderUserLocation(position) {
      const coords = position.coords || {};
      const lat = Number(coords.latitude);
      const lon = Number(coords.longitude);
      const accuracy = Number(coords.accuracy);
      console.info('FuelOpt geolocation result', {
        latitude: lat,
        longitude: lon,
        accuracy_m: Number.isFinite(accuracy) ? accuracy : null,
        fallback_used: false,
      });
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        console.warn('FuelOpt geolocation invalid coordinates; map center unchanged.', {
          latitude: coords.latitude,
          longitude: coords.longitude,
          fallback_used: false,
        });
        setRouteStatus('No se pudo obtener tu ubicación.', 'error');
        return;
      }
      const latLng = L.latLng(lat, lon);
      if (state.userLocationMarker) {
        state.userLocationMarker.setLatLng(latLng);
      } else {
        state.userLocationMarker = L.circleMarker(latLng, {
          pane: 'userLocationPane',
          radius: 7,
          color: '#fbf8f1',
          weight: 3,
          fillColor: '#16849a',
          fillOpacity: 1,
          interactive: false,
        }).addTo(map);
      }
      if (Number.isFinite(accuracy) && accuracy > 0) {
        if (state.userLocationAccuracyCircle) {
          state.userLocationAccuracyCircle.setLatLng(latLng);
          state.userLocationAccuracyCircle.setRadius(accuracy);
        } else {
          state.userLocationAccuracyCircle = L.circle(latLng, {
            pane: 'userLocationPane',
            radius: accuracy,
            color: '#16849a',
            weight: 1.5,
            opacity: .55,
            fillColor: '#16849a',
            fillOpacity: .20,
            interactive: false,
          }).addTo(map);
        }
      } else if (state.userLocationAccuracyCircle) {
        map.removeLayer(state.userLocationAccuracyCircle);
        state.userLocationAccuracyCircle = null;
      }
      const targetZoom = userLocationTargetZoom();
      map.setView(latLng, targetZoom, { animate: true });
      track('Geolocalización usada', { precision_m: String(Number.isFinite(accuracy) ? Math.round(accuracy) : -1) });
      if (Number.isFinite(accuracy) && accuracy > LOW_LOCATION_ACCURACY_M) {
        setRouteStatus('Ubicación aproximada: precisión baja.');
      } else {
        setRouteStatus('');
      }
    }

    function requestUserLocation(button) {
      if (!navigator.geolocation) {
        setRouteStatus(userLocationErrorMessage(), 'error');
        return;
      }
      button.disabled = true;
      button.classList.add('loading');
      setRouteStatus('Buscando tu ubicación...');
      navigator.geolocation.getCurrentPosition(
        (position) => {
          button.disabled = false;
          button.classList.remove('loading');
          renderUserLocation(position);
        },
        (error) => {
          console.warn('FuelOpt geolocation failed; map center unchanged.', {
            code: error?.code,
            message: error?.message,
            fallback_used: false,
          });
          button.disabled = false;
          button.classList.remove('loading');
          setRouteStatus(userLocationErrorMessage(error), 'error');
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 0,
        },
      );
    }

    function initUserLocationControl(mapInstance) {
      const UserLocationControl = L.Control.extend({
        options: { position: 'bottomleft' },
        onAdd() {
          const container = L.DomUtil.create('div', 'leaflet-control user-location-control');
          const button = L.DomUtil.create('button', 'user-location-button', container);
          button.type = 'button';
          button.setAttribute('aria-label', 'Centrar mapa en mi ubicación');
          button.setAttribute('title', 'Centrar mapa en mi ubicación');
          button.innerHTML = `
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="6"></circle>
              <circle cx="12" cy="12" r="2.2"></circle>
              <path d="M12 2.5v3.2M12 18.3v3.2M2.5 12h3.2M18.3 12h3.2"></path>
            </svg>
          `;
          L.DomEvent.disableClickPropagation(container);
          L.DomEvent.disableScrollPropagation(container);
          L.DomEvent.on(button, 'click', (event) => {
            L.DomEvent.preventDefault(event);
            requestUserLocation(button);
          });
          return container;
        },
      });
      return new UserLocationControl().addTo(mapInstance);
    }

    initUserLocationControl(map);

    function routeCoordKey(point) {
      return `${Number(point.lat).toFixed(6)},${Number(point.lon).toFixed(6)}`;
    }

    function selectedRouteKey() {
      if (!state.origin || !state.destination || !state.selectedStation) return '';
      return [
        routeCoordKey(state.origin),
        routeCoordKey(state.selectedStation),
        routeCoordKey(state.destination),
      ].join('|');
    }

    function clearCurrentRouteLayer() {
      // Immediately remove the route polyline from the map.
      // Safe to call when nothing is drawn (idempotent).
      // Does NOT touch routeRequestId — callers that start a new async
      // fetch will manage the sequence counter themselves.
      // Does NOT remove origin/destination/station markers.
      if (state.route) {
        map.removeLayer(state.route);
        state.route = null;
      }
      state.routeKey = '';
    }

    function clearSelectedRoute() {
      state.routeRequestId += 1;
      setRouteStatus('');
      clearCurrentRouteLayer();
    }

    function resetMapView() {
      map.setView([40.4168, -3.7038], 6);
    }

    function elementIsVisible(element) {
      if (!element || element.hidden) return false;
      const style = window.getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    function rectOverlaps(rect, mapRect) {
      return rect.right > mapRect.left && rect.left < mapRect.right && rect.bottom > mapRect.top && rect.top < mapRect.bottom;
    }

    function extendBoundsWithPoint(bounds, point) {
      if (!point) return bounds;
      const lat = Number(point.lat);
      const lon = Number(point.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return bounds;
      const latLng = L.latLng(lat, lon);
      return bounds ? bounds.extend(latLng) : L.latLngBounds(latLng, latLng);
    }

    function routeBoundsFromLayer(layer) {
      let bounds = null;
      if (layer && typeof layer.getBounds === 'function') {
        const layerBounds = layer.getBounds();
        if (layerBounds?.isValid()) {
          bounds = L.latLngBounds(layerBounds.getSouthWest(), layerBounds.getNorthEast());
        }
      } else if (layer && typeof layer.isValid === 'function' && layer.isValid()) {
        bounds = L.latLngBounds(layer.getSouthWest(), layer.getNorthEast());
      }
      bounds = extendBoundsWithPoint(bounds, state.origin);
      bounds = extendBoundsWithPoint(bounds, state.selectedStation);
      bounds = extendBoundsWithPoint(bounds, state.destination);
      return bounds;
    }

    function routeVisiblePadding() {
      const mapEl = map.getContainer();
      const mapRect = mapEl.getBoundingClientRect();
      const gap = desktopSidebarQuery.matches ? 36 : 22;

      // Left: config sidebar
      const sidebarEl = $('config_sidebar');
      let paddingLeft = 20;
      if (elementIsVisible(sidebarEl)) {
        const rect = sidebarEl.getBoundingClientRect();
        if (rectOverlaps(rect, mapRect) && rect.right < mapRect.left + mapRect.width * .68) {
          paddingLeft = Math.max(20, Math.ceil(rect.right - mapRect.left + gap));
        }
      }

      // Top: search bar, header, route status
      let paddingTop = 20;
      ['.map-top', '.app-header', '.map-search-card', '#route_status'].forEach(selector => {
        const element = document.querySelector(selector);
        if (!elementIsVisible(element)) return;
        const rect = element.getBoundingClientRect();
        if (!rectOverlaps(rect, mapRect)) return;
        paddingTop = Math.max(paddingTop, Math.ceil(rect.bottom - mapRect.top + gap));
      });

      // Right: result panel (only if visible and non-empty)
      const resultEl = $('result');
      let paddingRight = 20;
      const resultVisible = elementIsVisible(resultEl) && resultEl.getAttribute('data-empty') !== 'true';
      if (resultVisible) {
        const rect = resultEl.getBoundingClientRect();
        if (rectOverlaps(rect, mapRect)) {
          if (rect.left > mapRect.left + mapRect.width * .45) {
            paddingRight = Math.max(20, Math.ceil(mapRect.right - rect.left + gap));
          } else {
            // panel is at the bottom on mobile — add to bottom instead
            paddingRight = 20;
          }
        }
      }

      // Bottom: result panel on mobile (below centre)
      let paddingBottom = 20;
      if (resultVisible) {
        const rect = resultEl.getBoundingClientRect();
        if (rectOverlaps(rect, mapRect) && rect.left <= mapRect.left + mapRect.width * .45) {
          paddingBottom = Math.max(20, Math.ceil(mapRect.bottom - rect.top + gap));
        }
      }

      // Safety: usable area must be at least 200 x 150
      const usableW = mapRect.width - paddingLeft - paddingRight;
      const usableH = mapRect.height - paddingTop - paddingBottom;
      if (usableW < 200 || usableH < 150) {
        return { left: 80, top: 80, right: 80, bottom: 80 };
      }

      return { left: paddingLeft, top: paddingTop, right: paddingRight, bottom: paddingBottom };
    }

    function fitRouteToUsableViewport(boundsOrNull) {
      // A. Build bounds
      let bounds = null;
      if (boundsOrNull && typeof boundsOrNull.isValid === 'function' && boundsOrNull.isValid()) {
        bounds = boundsOrNull;
      } else if (boundsOrNull && typeof boundsOrNull.getBounds === 'function') {
        const lb = boundsOrNull.getBounds();
        if (lb?.isValid()) bounds = lb;
      } else {
        bounds = routeBoundsFromLayer(state.route);
      }
      bounds = extendBoundsWithPoint(bounds, state.origin);
      bounds = extendBoundsWithPoint(bounds, state.selectedStation);
      bounds = extendBoundsWithPoint(bounds, state.destination);
      if (!bounds?.isValid()) return;

      // B & C. Measure overlays and compute paddings
      const padding = routeVisiblePadding();

      // E. fitBounds
      map.fitBounds(bounds.pad(.08), {
        paddingTopLeft: [padding.left, padding.top],
        paddingBottomRight: [padding.right, padding.bottom],
        maxZoom: 15,
        animate: true,
      });
    }

    function fitBoundsToVisibleArea(bounds, options = {}) {
      if (!bounds?.isValid()) return;
      const padding = routeVisiblePadding();
      map.fitBounds(bounds.pad(.08), {
        animate: options.animate !== false,
        duration: options.animate === false ? 0 : .45,
        maxZoom: 15,
        paddingTopLeft: [padding.left, padding.top],
        paddingBottomRight: [padding.right, padding.bottom],
      });
    }

    function fitRouteToVisibleArea(layerOrBounds, options = {}) {
      const bounds = routeBoundsFromLayer(layerOrBounds);
      fitBoundsToVisibleArea(bounds, options);
    }

    function refitVisibleRoute(delayMs = 0) {
      const canFitRoutePoints = Boolean(state.origin && state.selectedStation && state.destination);
      if (!state.route && !canFitRoutePoints) return;
      if (!delayMs) {
        requestAnimationFrame(() => requestAnimationFrame(() => fitRouteToUsableViewport(null)));
        return;
      }
      setTimeout(() => {
        if (state.route || (state.origin && state.selectedStation && state.destination)) {
          requestAnimationFrame(() => requestAnimationFrame(() => fitRouteToUsableViewport(null)));
        }
      }, delayMs);
    }

    function scheduleMapViewportRefresh() {
      clearTimeout(mapResizeTimer);
      mapResizeTimer = setTimeout(() => {
        map.invalidateSize({ pan: false });
        if (state.route || (state.origin && state.selectedStation && state.destination)) {
          fitRouteToUsableViewport(null);
        }
      }, 180);
    }

    function fitRouteLayer(layer) {
      requestAnimationFrame(() => requestAnimationFrame(() => fitRouteToUsableViewport(layer)));
    }

    function drawStopoverRoute(data, fitBounds = true) {
      if (state.route) map.removeLayer(state.route);
      const group = L.featureGroup();
      const colors = ['#171411', '#9f7a3a'];
      (data.legs || []).forEach((leg, index) => {
        const latLngs = (leg.geometry || []).map(point => [point.lat, point.lon]);
        if (latLngs.length < 2) return;
        L.polyline(latLngs, {
          color: '#fbf8f1',
          weight: 9,
          opacity: .95,
          lineCap: 'round',
          lineJoin: 'round',
          interactive: false,
          pane: 'routePane',
        }).addTo(group);
        L.polyline(latLngs, {
          color: colors[index] || '#2f5f4f',
          weight: 5,
          opacity: .95,
          lineCap: 'round',
          lineJoin: 'round',
          interactive: false,
          pane: 'routePane',
        }).addTo(group);
      });
      if (!group.getLayers().length) {
        clearSelectedRoute();
        setRouteStatus('No se pudo pintar la ruta.', 'error');
        if (fitBounds) fitRouteToUsableViewport(null);
        return;
      }
      state.route = group.addTo(map);
      setRouteStatus('');
      if (fitBounds) fitRouteLayer(group);
    }

    async function refreshSelectedRoute({ fitBounds = true } = {}) {
      const key = selectedRouteKey();
      if (!key) {
        clearSelectedRoute();
        return false;
      }
      if (state.route && state.routeKey === key) {
        if (fitBounds) fitRouteLayer(state.route);
        return true;
      }
      const requestId = state.routeRequestId + 1;
      state.routeRequestId = requestId;
      state.routeKey = key;
      setRouteStatus('Calculando ruta...');
      const payload = {
        origin_lat: state.origin.lat,
        origin_lon: state.origin.lon,
        station_lat: state.selectedStation.lat,
        station_lon: state.selectedStation.lon,
        destination_lat: state.destination.lat,
        destination_lon: state.destination.lon,
      };
      try {
        const response = await fetch('/route/stopover', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await readJsonOrError(response);
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo calcular la ruta');
        if (requestId !== state.routeRequestId) return true;
        drawStopoverRoute(data, fitBounds);
      } catch (error) {
        if (requestId !== state.routeRequestId) return true;
        if (state.route) {
          map.removeLayer(state.route);
          state.route = null;
        }
        setRouteStatus('Ruta no disponible', 'error');
        if (fitBounds) fitRouteToUsableViewport(null);
      }
      return true;
    }

    function renderSelectedStationMarker(station) {
      if (state.markers.station) map.removeLayer(state.markers.station);
      if (!station) {
        state.markers.station = null;
        return null;
      }
      state.markers.station = L.marker([station.lat, station.lon], {
        icon: icons.station,
        pane: 'selectedStationPane',
        zIndexOffset: 1000,
      }).addTo(map);
      return state.markers.station;
    }

    function pointPlaceholder(point) {
      return point === 'origin' ? '¿Desde dónde sales?' : '¿A dónde vas?';
    }

    function coordinateLabel(lat, lon) {
      return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    }

    function mapSelectedLabel(point) {
      return `${point === 'origin' ? 'Salida' : 'Llegada'} - Seleccionado en el mapa`;
    }

    function placeDisplayLabel(place) {
      if (!place) return '';
      return place.label || place.title || place.name || coordinateLabel(place.lat, place.lon);
    }

    function syncPointUI(point) {
      const place = state[point];
      const label = place ? placeDisplayLabel(place) : pointPlaceholder(point);
      const choiceEl = $(`${point}_choice`);
      choiceEl.textContent = label;
      choiceEl.classList.toggle('is-placeholder', !place);
      if (state.active === point) {
        // Only overwrite the input value when a place has been selected.
        // When the user is actively typing (isTyping) and no place is selected
        // yet, preserve whatever they have typed so far.
        if (place) {
          $('map_search').value = placeDisplayLabel(place);
          isTyping = false;
        } else if (!isTyping) {
          $('map_search').value = '';
        }
        $('map_choice').textContent = label;
      }
    }

    function syncAllPointUI() {
      syncPointUI('origin');
      syncPointUI('destination');
    }

    function mirrorDestinationToOrigin() {
      if (!state.origin) return;
      state.destination = { ...state.origin, label: placeDisplayLabel(state.origin) };
      syncPointUI('destination');
      if (state.markers.destination) {
        map.removeLayer(state.markers.destination);
        state.markers.destination = null;
      }
    }

    function setInputMode(mode) {
      state.inputMode = mode === 'budget' ? 'budget' : 'liters';
      syncRefuelInputUI();
    }

    function syncRefuelInputUI() {
      const isBudget = state.inputMode === 'budget';
      $('refill_mode_liters').classList.toggle('active', !isBudget);
      $('refill_mode_budget').classList.toggle('active', isBudget);
      $('refill_mode_liters').setAttribute('aria-pressed', String(!isBudget));
      $('refill_mode_budget').setAttribute('aria-pressed', String(isBudget));
      $('liters').placeholder = isBudget ? 'Ej. 40' : 'Ej. 30';
      $('liters').setAttribute('aria-label', isBudget ? 'Importe en euros' : 'Litros a repostar');
      $('refuel_amount_hint').textContent = isBudget
        ? 'Presupuesto total que quieres gastar.'
        : 'Cantidad de combustible a repostar.';
    }

    function metricSvgIcon(innerHtml) {
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${innerHtml}</svg>`;
    }

    const METRIC_ICONS = {
      detour:       metricSvgIcon('<polygon points="3 11 22 2 13 21 11 13 3 11"/>'),
      fuel:         metricSvgIcon('<line x1="3" y1="22" x2="15" y2="22"/><line x1="4" y1="9" x2="14" y2="9"/><path d="M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18"/><path d="M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2a2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 5"/>'),
      tag:          metricSvgIcon('<path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/><path d="M7 7h.01"/>'),
      trendingDown: metricSvgIcon('<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>'),
      receipt:      metricSvgIcon('<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1Z"/><path d="M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8"/><path d="M12 17V7"/>'),
    };

    const INFO_TOOLTIP_TEXTS = {
      ahorro: 'Compara el precio de esta estación con la alternativa de referencia y descuenta el coste real del desvío, según los litros a repostar, tu consumo medio y la distancia extra.',
      precio: 'Precios oficiales del Ministerio para la Transición Ecológica. Pueden no ser 100% precisos.',
    };

    function infoIconHtml(key, placement = 'above') {
      const text = escapeHtml(INFO_TOOLTIP_TEXTS[key] || '');
      const cls = placement === 'below' ? 'info-icon info-icon--below' : 'info-icon';
      return `<button class="${cls}" type="button" tabindex="0" aria-label="Más información"><svg class="info-icon__svg" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 7.5v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="5" r="0.85" fill="currentColor"/></svg><span class="info-tooltip" role="tooltip">${text}</span></button>`;
    }

    function resultCloseButton() {
      return '<button id="close_result" class="result-close" type="button" aria-label="Cerrar resultados" title="Cerrar resultados">×</button>';
    }

    function bindResultCloseButton() {
      const button = $('close_result');
      if (button) button.addEventListener('click', closeResultPanel);
    }

    function closeResultPanel() {
      clearSelectedRoute();
      if (state.markers.station) {
        map.removeLayer(state.markers.station);
        state.markers.station = null;
      }
      state.selectedStation = null;
      state.alternativesOpen = false;
      state.resultHasFit = false;
      const result = $('result');
      result.innerHTML = '';
      result.setAttribute('data-empty', 'true');
      result.classList.remove('result-panel--expanded', 'result-panel--collapsed');
    }

    function setActive(point) {
      if (state.active !== point) isTyping = false;
      state.active = point;
      $('tab_origin').classList.toggle('active', point === 'origin');
      $('tab_destination').classList.toggle('active', point === 'destination');
      const inputSlot = $(`${point}_input_slot`);
      const searchInput = document.querySelector('.map-search-input');
      if (inputSlot && searchInput && searchInput.parentElement !== inputSlot) {
        inputSlot.appendChild(searchInput);
      }
      $('map_search_label').textContent = point === 'origin' ? 'Salida' : 'Llegada';
      $('map_search').placeholder = point === 'origin' ? '¿Desde dónde sales?' : '¿A dónde vas?';
      $('map_search').setAttribute('aria-label', point === 'origin' ? 'Salida' : 'Llegada');
      const searchCard = document.querySelector('.map-search-card');
      if (searchCard) searchCard.dataset.activePoint = point;
      syncPointUI(point);
      clearSuggestions();
    }

    async function reverseGeocodePoint(point, lat, lon) {
      const requestId = state.reverseGeocodeRequestId + 1;
      state.reverseGeocodeRequestId = requestId;
      try {
        const url = new URL('/reverse-geocode', window.location.origin);
        url.searchParams.set('lat', lat.toFixed(6));
        url.searchParams.set('lon', lon.toFixed(6));
        const response = await fetch(url);
        const data = await readJsonOrError(response);
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo resolver la ubicación');
        if (requestId !== state.reverseGeocodeRequestId) return;
        const item = data.item;
        if (!item) return;
        const current = state[point];
        if (!current) return;
        if (Math.abs(current.lat - lat) > 1e-6 || Math.abs(current.lon - lon) > 1e-6) return;
        const resolvedLabel = item.label || item.title || item.name || coordinateLabel(current.lat, current.lon);
        setPoint(point, {
          ...current,
          ...item,
          label: resolvedLabel,
          lat: current.lat,
          lon: current.lon,
        });
      } catch (_) {
      }
    }

    function setPoint(point, place) {
      state[point] = place;
      syncPointUI(point);
      if (state.markers[point]) map.removeLayer(state.markers[point]);
      state.markers[point] = L.marker([place.lat, place.lon], { icon: icons[point] }).addTo(map);
      if ($('return_to_origin').checked && point === 'origin') {
        mirrorDestinationToOrigin();
        if (state.selectedStation && state.origin && state.destination) {
          refreshSelectedRoute({ fitBounds: true });
        } else {
          clearSelectedRoute();
          const group = Object.values(state.markers).filter(Boolean);
          if (group.length) fitBoundsToVisibleArea(L.featureGroup(group).getBounds().pad(.35));
        }
        return;
      }
      if (state.selectedStation && state.origin && state.destination) {
        refreshSelectedRoute({ fitBounds: true });
      } else {
        clearSelectedRoute();
        const group = Object.values(state.markers).filter(Boolean);
        if (group.length) fitBoundsToVisibleArea(L.featureGroup(group).getBounds().pad(.35));
      }
    }

    function clearSuggestions() {
      const box = $('map_suggestions');
      box.parentElement.style.display = 'none';
      box.innerHTML = '';
      box.style.display = 'none';
    }

    function suggestionsAreOpen() {
      const box = $('map_suggestions');
      return Boolean(box && box.style.display !== 'none' && box.parentElement.style.display !== 'none' && box.innerHTML.trim());
    }

    function rerankSuggestions(items, rawQuery, limit = 7) {
      function normalize(str) {
        return String(str || '').toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
      }
      function tokenize(str) {
        return normalize(str).split(/[\s,.\-/]+/).filter(t => t.length > 1);
      }
      function streetType(str) {
        const tokens = new Set(tokenize(str));
        const types = [
          ['travesia', ['travesia', 'trv']],
          ['avenida', ['avenida', 'avda', 'av']],
          ['calle', ['calle', 'cl']],
          ['plaza', ['plaza', 'plz']],
          ['paseo', ['paseo', 'ps']],
          ['camino', ['camino']],
          ['carretera', ['carretera', 'ctra']],
          ['ronda', ['ronda']],
          ['glorieta', ['glorieta']],
        ];
        const found = types.find(([, aliases]) => aliases.some(alias => tokens.has(alias)));
        return found ? found[0] : '';
      }
      function houseNumber(str) {
        const match = normalize(str).match(/(?:^|[\s,])(\d+[a-z]?)(?=$|[\s,])/i);
        return match ? match[1] : '';
      }
      function signature(item, keepNumber) {
        const title = normalize(item.title || item.name || item.label || '')
          .replace(/\b(de|del|la|el|los|las)\b/g, ' ')
          .replace(keepNumber ? /$^/ : /\b\d+[a-z]?\b/g, ' ')
          .replace(/\s+/g, ' ')
          .trim();
        const place = normalize(item.subtitle || item.label || '')
          .split(',')
          .slice(-2)
          .join(',')
          .trim();
        return `${item.layer || ''}|${title}|${place}`;
      }
      const stopWords = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'una', 'uno']);
      const qTokens = tokenize(rawQuery).filter(token => !stopWords.has(token));
      if (!qTokens.length) return items.slice(0, limit);
      const qType = streetType(rawQuery);
      const qNumber = houseNumber(rawQuery);
      const qText = normalize(rawQuery).replace(/\b\d+[a-z]?\b/g, '').replace(/\s+/g, ' ').trim();
      if (!qType && !qNumber && qTokens.length <= 1) return items.slice(0, limit);
      const scored = items
        .map(item => {
          const titleText = item.title || item.name || item.label || '';
          const subtitleText = item.subtitle || item.label || '';
          const combinedText = `${titleText} ${subtitleText}`;
          const nameTokens = tokenize(titleText);
          const addrTokens = tokenize(subtitleText);
          let nameHits = 0;
          let addrHits = 0;
          for (const qt of qTokens) {
            if (nameTokens.some(t => t.startsWith(qt) || qt.startsWith(t))) nameHits++;
            else if (addrTokens.some(t => t.startsWith(qt) || qt.startsWith(t))) addrHits++;
          }
          const coverage = (nameHits + addrHits * 0.5) / qTokens.length;
          const itemType = streetType(combinedText);
          const itemNumber = houseNumber(combinedText);
          let score = nameHits * 2 + addrHits + coverage;
          if (qText && normalize(combinedText).includes(qText)) score += 3;
          if (item.layer === 'address') score += qNumber ? 2 : 0.5;
          if (item.layer === 'venue') score += 1.2;
          if (item.layer === 'locality' || item.layer === 'region' || item.layer === 'country') score -= 3;
          if (qType) {
            if (itemType === qType) score += 6;
            else if (itemType) score -= 5;
            else score -= 1.5;
          }
          if (qNumber) {
            if (itemNumber === qNumber) score += 4;
            else if (itemNumber) score -= 2.5;
            else score -= 0.5;
          }
          score -= Number(item.rank || 0) * 0.02;
          return { item, score, itemType };
        })
        .sort((a, b) => b.score - a.score);
      const bestScore = scored[0]?.score ?? 0;
      const strictQuery = qType || qNumber || qTokens.length >= 3;
      function dedupe(entries, maxItems) {
        const seen = new Set();
        return entries
          .filter(entry => {
            const key = signature(entry.item, Boolean(qNumber));
            if (!key || seen.has(key)) return false;
            seen.add(key);
            return true;
          })
          .slice(0, maxItems)
          .map(entry => entry.item);
      }
      const filtered = scored
        .filter(entry => {
          if (!strictQuery) return true;
          if (entry.score < Math.max(0.5, bestScore - 5.5)) return false;
          if (qType && bestScore > 4 && entry.itemType && entry.itemType !== qType && entry.score < bestScore - 2) return false;
          return true;
        });
      const ranked = dedupe(filtered, limit);
      if (ranked.length) return ranked;
      return dedupe(scored, Math.min(3, limit));
    }

    function geocodeErrorMessage(data, fallback = 'No se pudo buscar el lugar') {
      const detail = data && data.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        const parts = detail
          .map(item => {
            if (typeof item === 'string') return item;
            if (item && typeof item === 'object') return item.msg || item.message || '';
            return '';
          })
          .filter(Boolean);
        return parts.length ? parts.join(' - ') : fallback;
      }
      if (detail && typeof detail === 'object') return detail.message || detail.msg || fallback;
      return fallback;
    }

    function isLegacySizeValidationError(data) {
      return /less than or equal to 10|menor o igual.*10|<=\s*10/i.test(geocodeErrorMessage(data, ''));
    }

    async function fetchGeocodeData(url, signal) {
      const response = await fetch(url, { signal });
      let data = {};
      try {
        data = await response.json();
      } catch {
        data = {};
      }
      return { response, data };
    }

    let searchRequestId = 0;
    let searchAbortController = null;
    let lastSuggestionDismissedAt = 0;
    const SEARCH_TIMEOUT_MS = 7000;

    function dismissSearchSuggestions() {
      if (!suggestionsAreOpen()) return false;
      clearTimeout(searchTimer);
      searchRequestId += 1;
      if (searchAbortController) {
        searchAbortController.abort();
        searchAbortController = null;
      }
      isTyping = false;
      clearSuggestions();
      syncPointUI(state.active);
      $('map_search').blur();
      lastSuggestionDismissedAt = Date.now();
      return true;
    }

    async function searchPlaces() {
      const requestId = ++searchRequestId;
      if (searchAbortController) {
        searchAbortController.abort();
        searchAbortController = null;
      }
      const point = state.active;
      const input = $('map_search');
      const q = input.value.trim();
      if (q.length < 3) {
        clearSuggestions();
        return;
      }
      const box = $('map_suggestions');
      box.parentElement.style.display = 'block';
      box.style.display = 'block';
      box.innerHTML = '<button class="suggestion" type="button">Buscando...</button>';
      const controller = new AbortController();
      searchAbortController = controller;
      const timeoutId = window.setTimeout(() => controller.abort(), SEARCH_TIMEOUT_MS);
      try {
        const center = map.getCenter();
        const url = new URL('/geocode', window.location.origin);
        url.searchParams.set('q', q);
        url.searchParams.set('size', '15');
        url.searchParams.set('focus_lat', center.lat.toFixed(6));
        url.searchParams.set('focus_lon', center.lng.toFixed(6));
        let { response, data } = await fetchGeocodeData(url, controller.signal);
        if (requestId !== searchRequestId) return;
        if (!response.ok && isLegacySizeValidationError(data)) {
          url.searchParams.set('size', '10');
          ({ response, data } = await fetchGeocodeData(url, controller.signal));
          if (requestId !== searchRequestId) return;
        }
        if (!response.ok) throw new Error(geocodeErrorMessage(data));
        if (!Array.isArray(data.items) || !data.items.length) {
          box.innerHTML = '<button class="suggestion" type="button">Sin resultados</button>';
          return;
        }
        const ranked = rerankSuggestions(data.items, q, 7);
        if (!ranked.length) {
          box.innerHTML = '<button class="suggestion" type="button">Sin coincidencias precisas</button>';
          return;
        }
        box.innerHTML = ranked.map(renderSuggestion).join('');
        [...box.querySelectorAll('[data-idx]')].forEach(button => {
          button.addEventListener('click', () => {
            setPoint(point, ranked[Number(button.dataset.idx)]);
            clearSuggestions();
          });
        });
      } catch (error) {
        if (requestId !== searchRequestId) return;
        if (error.name === 'AbortError') {
          box.innerHTML = '<button class="suggestion" type="button">La búsqueda tarda demasiado. Prueba con menos detalle.</button>';
          return;
        }
        box.innerHTML = `<button class="suggestion" type="button">${escapeHtml(error.message)}</button>`;
      } finally {
        window.clearTimeout(timeoutId);
        if (searchAbortController === controller) searchAbortController = null;
      }
    }

    let searchTimer = null;
    let isTyping = false;
    $('map_search').addEventListener('input', () => {
      isTyping = true;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(searchPlaces, 420);
    });
    $('map_search').addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      clearTimeout(searchTimer);
      searchPlaces();
    });

    map.on('dblclick', (event) => {
      if (Date.now() - lastSuggestionDismissedAt < 600) return;
      const point = state.active;
      const lat = event.latlng.lat;
      const lon = event.latlng.lng;
      setPoint(point, {
        label: mapSelectedLabel(point),
        lat,
        lon,
      });
      reverseGeocodePoint(point, lat, lon);
    });
    map.on('click', (event) => {
      if (!dismissSearchSuggestions()) return;
      if (event.originalEvent) {
        event.originalEvent.preventDefault();
        event.originalEvent.stopPropagation();
      }
    });

    function syncReturnMode() {
      const same = $('return_to_origin').checked;
      const searchCard = document.querySelector('.map-search-card');
      if (searchCard) searchCard.classList.toggle('return-mode', same);
      $('destination_block').style.display = same ? 'none' : '';
      $('tab_destination').style.display = '';
      if (same && state.origin) {
        mirrorDestinationToOrigin();
        if (state.selectedStation) refreshSelectedRoute({ fitBounds: true });
      }
      if (same && !state.origin) {
        state.destination = null;
        if (state.markers.destination) {
          map.removeLayer(state.markers.destination);
          state.markers.destination = null;
        }
      }
      syncAllPointUI();
      setActive(same ? 'origin' : 'destination');
    }

    $('tab_origin').addEventListener('click', () => setActive('origin'));
    $('tab_destination').addEventListener('click', () => setActive('destination'));
    $('tab_origin').addEventListener('keydown', (event) => {
      if (event.target !== $('tab_origin')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      setActive('origin');
      $('map_search').focus();
    });
    $('tab_destination').addEventListener('keydown', (event) => {
      if (event.target !== $('tab_destination')) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      setActive('destination');
      $('map_search').focus();
    });
    $('return_to_origin').addEventListener('change', syncReturnMode);
    desktopSidebarQuery.addEventListener('change', () => setSidebarCollapsed(state.sidebarCollapsed));
    window.addEventListener('resize', scheduleMapViewportRefresh);
    $('search_trigger').addEventListener('click', () => {
      clearTimeout(searchTimer);
      searchPlaces();
    });
    $('refill_mode_liters').addEventListener('click', () => setInputMode('liters'));
    $('refill_mode_budget').addEventListener('click', () => {
      setInputMode('budget');
      track('Modo presupuesto activado');
    });

    syncRefuelInputUI();
    syncAllPointUI();
    setActive('origin');
    syncReturnMode();

    // ─── Custom dropdown (pdd) ───────────────────────────────────────

    function getPddValue(id) {
      const el = $(id);
      return el ? (el.dataset.value || '') : '';
    }

    function setPddValue(id, value, label) {
      const el = $(id);
      if (!el) return;
      el.dataset.value = value;
      const sel = el.querySelector('.pdd-selected');
      if (sel) sel.textContent = label;
      // Options may be in portaled menu — find via stored reference
      const menu = el._pddMenu || el.querySelector('.pdd-menu');
      if (menu) {
        menu.querySelectorAll('.pdd-option').forEach(opt => {
          const active = opt.dataset.value === value;
          opt.classList.toggle('active', active);
          opt.setAttribute('aria-selected', String(active));
        });
      }
    }

    function closePDD(el) {
      el.classList.remove('is-open');
      const trigger = el.querySelector('.pdd-trigger');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
      // Return portaled menu back to its original parent
      const menu = el._pddMenu;
      if (menu && menu.parentElement !== el) {
        menu.removeAttribute('data-pdd-portal');
        menu.style.cssText = '';
        el.appendChild(menu);
      }
    }

    function openPDD(el) {
      document.querySelectorAll('.pdd.is-open').forEach(other => {
        if (other !== el) closePDD(other);
      });
      el.classList.add('is-open');
      const trigger = el.querySelector('.pdd-trigger');
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
      // Portal the menu to .side so it escapes all nested stacking contexts
      const menu = el._pddMenu;
      const side = el.closest('.side');
      if (menu && side) {
        const tRect = trigger.getBoundingClientRect();
        const sRect = side.getBoundingClientRect();
        menu.dataset.pddPortal = el.id;
        menu.style.cssText = [
          'position:absolute',
          `top:${tRect.bottom - sRect.top}px`,
          `left:${tRect.left - sRect.left}px`,
          `width:${tRect.width}px`,
          'right:auto',
          'z-index:9999',
        ].join(';');
        side.appendChild(menu);
      }
    }

    function initPDD(id) {
      const el = $(id);
      if (!el || el._pddInit) return;
      el._pddInit = true;
      const trigger = el.querySelector('.pdd-trigger');
      // Store menu reference — it will move in the DOM but the JS reference stays valid
      el._pddMenu = el.querySelector('.pdd-menu');
      const menu = el._pddMenu;

      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        el.classList.contains('is-open') ? closePDD(el) : openPDD(el);
      });

      trigger.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          el.classList.contains('is-open') ? closePDD(el) : openPDD(el);
        }
        if (e.key === 'Escape') closePDD(el);
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (!el.classList.contains('is-open')) openPDD(el);
          menu?.querySelector('.pdd-option')?.focus();
        }
      });

      // Option click: attached to menu element directly so it works after portal
      if (menu) {
        menu.addEventListener('click', (e) => {
          e.stopPropagation();
          const opt = e.target.closest('.pdd-option');
          if (!opt) return;
          const rawLabel = opt.childNodes[0]?.textContent?.trim() || opt.textContent.trim();
          setPddValue(id, opt.dataset.value, rawLabel);
          closePDD(el);
          trigger.focus();
        });

        menu.addEventListener('keydown', (e) => {
          const opts = [...menu.querySelectorAll('.pdd-option')];
          const idx = opts.indexOf(document.activeElement);
          if (e.key === 'ArrowDown') { e.preventDefault(); opts[Math.min(idx + 1, opts.length - 1)]?.focus(); }
          if (e.key === 'ArrowUp')   { e.preventDefault(); (idx <= 0 ? trigger : opts[idx - 1])?.focus(); }
          if (e.key === 'Escape')    { closePDD(el); trigger.focus(); }
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const opt = document.activeElement;
            if (opt?.classList.contains('pdd-option')) {
              const rawLabel = opt.childNodes[0]?.textContent?.trim() || opt.textContent.trim();
              setPddValue(id, opt.dataset.value, rawLabel);
              closePDD(el);
              trigger.focus();
            }
          }
        });
      }
    }

    function setPddOptions(id, options) {
      const el = $(id);
      if (!el) return;
      const menu = el.querySelector('.pdd-menu');
      if (!menu) return;
      const first = options[0];
      if (first && !el.dataset.value) {
        el.dataset.value = first.key;
        const sel = el.querySelector('.pdd-selected');
        if (sel) sel.textContent = first.label;
      }
      const currentValue = el.dataset.value;
      menu.innerHTML = options.map(opt => {
        const active = opt.key === currentValue;
        return `<div class="pdd-option${active ? ' active' : ''}" data-value="${escapeHtml(opt.key)}" role="option" aria-selected="${active}" tabindex="-1">${escapeHtml(opt.label)}</div>`;
      }).join('');
    }

    document.addEventListener('click', () => {
      document.querySelectorAll('.pdd.is-open').forEach(closePDD);
      document.querySelectorAll('.info-icon.is-open').forEach(el => el.classList.remove('is-open'));
    });

    // Mobile tap toggle for info tooltips — delegated on the persistent result container
    $('result').addEventListener('click', (e) => {
      const icon = e.target.closest('.info-icon');
      if (!icon) return;
      e.stopPropagation();
      const wasOpen = icon.classList.contains('is-open');
      document.querySelectorAll('.info-icon.is-open').forEach(el => el.classList.remove('is-open'));
      if (!wasOpen) icon.classList.add('is-open');
    });

    // Mobile tap toggle for info tooltips — sidebar icons
    $('config_sidebar').addEventListener('click', (e) => {
      const icon = e.target.closest('.info-icon');
      if (!icon) return;
      e.stopPropagation();
      const wasOpen = icon.classList.contains('is-open');
      document.querySelectorAll('.info-icon.is-open').forEach(el => el.classList.remove('is-open'));
      if (!wasOpen) icon.classList.add('is-open');
    });

    // ─────────────────────────────────────────────────────────────────

    async function loadOptions() {
      const [fuels, brands] = await Promise.all([
        fetch('/fuels').then(r => r.json()),
        fetch('/brands').then(r => r.json()),
      ]);
      setPddOptions('fuel_type', fuels.fuels);
      renderBrands(brands.brands || []);
    }

    $('select_all_brands').addEventListener('click', () => {
      const shouldSelectAll = !allBrandsSelected();
      brandInputs().forEach(input => {
        input.checked = shouldSelectAll;
      });
      state.brandFilterMode = shouldSelectAll ? 'all' : 'manual';
      $('status').textContent = '';
      updateBrandFilterState();
    });

    $('brand_checks').addEventListener('change', (event) => {
      const input = event.target;
      if (!input.matches('[name="brand_filter"]')) return;
      if (state.brandFilterMode === 'all' && !input.checked) {
        state.brandFilterMode = 'all_except';
      } else if (state.brandFilterMode === 'all_except') {
        state.brandFilterMode = allBrandsSelected() ? 'all' : 'all_except';
      } else if (allBrandsSelected()) {
        state.brandFilterMode = 'all';
      }
      const selected = selectedBrands();
      const excluded = excludedBrands();
      if (state.brandFilterMode === 'manual' && shouldUseBrandExclusions(selected, excluded)) {
        state.brandFilterMode = 'all_except';
      }
      if (state.brandFilterMode === 'manual' && input.checked && selected.length > 10 && !allBrandsSelected()) {
        input.checked = !input.checked;
        $('status').textContent = 'Puedes elegir hasta 10 marcas concretas. Usa "Todas" para buscar en todo el catalogo.';
      } else {
        $('status').textContent = '';
      }
      updateBrandFilterState();
    });

    function candidateBudget(item) {
      const value = Number(item.budget_amount_eur);
      return Number.isFinite(value) && value > 0 ? value : null;
    }

    function candidateGrossLiters(item) {
      const value = Number(item.gross_refuel_liters);
      if (Number.isFinite(value) && value > 0) return value;
      const budget = candidateBudget(item);
      const price = Number(item.price_eur_l);
      return budget && Number.isFinite(price) && price > 0 ? budget / price : 0;
    }

    function routeSourceNote(data, selected) {
      const routeSource = String(data.route_source || selected.route_source || '').toLowerCase();
      if (!routeSource) return '';
      if (routeSource.includes('openrouteservice')) {
        return '';
      }
      return `<div class="result-note"><strong>Fuente de ruta:</strong> ${escapeHtml(routeSource)}</div>`;
    }

    function warningByCode(warnings, code) {
      if (!Array.isArray(warnings)) return null;
      return warnings.find(warning => warning && typeof warning === 'object' && warning.code === code) || null;
    }

    function renderWarnings(warnings) {
      if (!Array.isArray(warnings)) return '';
      const hiddenCodes = new Set(['catalog_degraded', 'stale_reference_prices']);
      if (warningByCode(warnings, 'brand_filter_too_restrictive')) {
        hiddenCodes.add('independent_brands_excluded_or_hidden');
      }
      return warnings.map((warning) => {
        if (typeof warning === 'string' && warning.trim()) {
          return `
            <div class="result-warning result-warning--info">
              <strong>Aviso</strong>
              <p>${escapeHtml(warning)}</p>
            </div>
          `;
        }
        if (!warning || typeof warning !== 'object') return '';
        if (hiddenCodes.has(warning.code)) return '';
        const severity = ['info', 'warning', 'critical'].includes(warning.severity) ? warning.severity : 'info';
        const classBySeverity = {
          info: 'result-warning--info',
          warning: 'result-warning--warning',
          critical: 'result-warning--critical',
        };
        const titleFallbacks = {
          using_haversine_estimate: 'Ruta estimada por distancia',
        };
        const title = String(warning.title || titleFallbacks[warning.code] || '').trim();
        const message = String(warning.message || '').trim();
        if (!title || !message) return '';
        return `
          <div class="result-warning ${classBySeverity[severity]}">
            <strong>${escapeHtml(title)}</strong>
            <p>${escapeHtml(message)}</p>
          </div>
        `;
      }).filter(Boolean).join('');
    }

    function priceMetricHtml(price, warnings) {
      const staleWarning = warningByCode(warnings, 'stale_reference_prices');
      const hasOfficialReference = Boolean(catalogValue(lastCatalogStatus, 'source_reference_date'));
      const hasDownloadedPrices = Boolean(
        catalogValue(lastCatalogStatus, 'source_fetched_at')
        || catalogValue(lastCatalogStatus, 'source_fetch_completed_at')
      );
      const missingOfficialDate = Boolean(lastCatalogStatus && hasDownloadedPrices && !hasOfficialReference);
      const warningTitle = missingOfficialDate ? 'Fecha oficial no disponible' : 'Precios de referencia anteriores';
      const warningCopy = missingOfficialDate
        ? 'MINETUR no informa una fecha oficial por precio. El cálculo usa los últimos datos descargados por FuelOpt.'
        : 'El cálculo usa la última fecha oficial disponible en la fuente.';
      const priceWarning = (missingOfficialDate || staleWarning) ? `
        <span class="price-warning" tabindex="0" aria-label="Aviso: ${escapeHtml(warningTitle)}" title="${escapeHtml(warningTitle)}">
          <span class="warning-triangle" aria-hidden="true">
            <svg class="warning-triangle__svg" viewBox="0 0 32 28" focusable="false" aria-hidden="true">
              <polygon
                class="warning-triangle__shape"
                points="16 2 30 26 2 26"
              />
              <rect class="warning-triangle__bar" x="14.4" y="9.5" width="3.2" height="8.8" rx="0.9" />
              <rect class="warning-triangle__dot" x="14.4" y="21" width="3.2" height="3.2" rx="0.6" />
            </svg>
          </span>
          <span class="price-warning-tooltip" role="tooltip">
            <strong>${escapeHtml(warningTitle)}</strong>
            <span>${escapeHtml(warningCopy)}</span>
          </span>
        </span>
      ` : '';
      return `
        <div class="metric metric--price">
          <span class="metric-icon" aria-hidden="true">${METRIC_ICONS.tag}</span>
          <span class="metric-label">Precio actual ${infoIconHtml('precio')}</span>
          <div class="metric-value-row metric-value-row--price">
            <strong>${fmtPrice(price)}</strong>
          </div>
        </div>
      `;
    }

    function stationDetailLine(station) {
      return [station.address, station.municipality].filter(Boolean).join(' · ');
    }

    function stationLogoHtml(station, className = 'result-station-logo') {
      const logoSrc = brandLogoFor(station.brand_canonical || station.brand || station.name || '');
      const alt = station.brand_canonical || station.brand || station.name || 'Gasolinera';
      return `
        <span class="${className}">
          <img src="${escapeHtml(logoSrc)}" alt="${escapeHtml(alt)}" loading="lazy" onerror="this.src='${BRAND_LOGO_FALLBACK}'">
        </span>
      `;
    }

    function formattedSignedEuro(value) {
      const amount = Number(value || 0);
      return amount >= 0 ? fmtEuro(amount) : `-${fmtEuro(Math.abs(amount))}`;
    }

    function savingsPerLiter(item, saving) {
      const liters = candidateGrossLiters(item);
      const amount = Number(saving || 0);
      return liters > 0 && Number.isFinite(amount) ? amount / liters : null;
    }

    function formattedSignedPrice(value) {
      if (!Number.isFinite(value)) return '—';
      return value >= 0 ? fmtPrice(value) : `-${fmtPrice(Math.abs(value))}`;
    }

    function renderSelectedStationSummary(station) {
      const stationName = escapeHtml(station.name || 'Estación seleccionada');
      const rawBrand = String(station.brand_canonical || station.brand || '').trim();
      const brandName = escapeHtml(rawBrand || 'Marca no identificada');
      const stationLocation = stationDetailLine(station);
      const stationIncludesBrand = rawBrand && String(station.name || '').toUpperCase().includes(rawBrand.toUpperCase());
      const stationMeta = [
        stationIncludesBrand ? '' : brandName,
        stationLocation ? escapeHtml(stationLocation) : '',
      ].filter(Boolean).join(' · ');
      return `
        <div class="metric metric--station">
          <span class="metric-icon" aria-hidden="true">${METRIC_ICONS.fuel}</span>
          <div class="result-station-copy">
            <span class="result-section-label">Estación seleccionada</span>
            <h2>${stationName}</h2>
            ${stationMeta ? `<p class="result-station-location">${stationMeta}</p>` : ''}
          </div>
          ${stationLogoHtml(station)}
        </div>
      `;
    }

    function renderResultMetricRows(selected, warnings, saving) {
      const perLiterSaving = savingsPerLiter(selected, saving);
      return `
        <div class="metric">
          <span class="metric-icon" aria-hidden="true">${METRIC_ICONS.detour}</span>
          <span class="metric-label">Distancia extra</span>
          <strong>${fmtKm(selected.extra_detour_km)}</strong>
        </div>
        ${renderSelectedStationSummary(selected.station || {})}
        ${priceMetricHtml(selected.price_eur_l, warnings)}
        ${perLiterSaving !== null ? `
          <div class="metric saving">
            <span class="metric-icon" aria-hidden="true">${METRIC_ICONS.trendingDown}</span>
            <span class="metric-label">Ahorro por litro</span>
            <strong${perLiterSaving !== null ? ` style="color:${perLiterSaving > 0 ? '#2D7A4F' : perLiterSaving < 0 ? '#C0392B' : '#6B6560'}"` : ''}>${formattedSignedPrice(perLiterSaving)}</strong>
          </div>
        ` : ''}
        <div class="metric">
          <span class="metric-icon" aria-hidden="true">${METRIC_ICONS.receipt}</span>
          <span class="metric-label">Coste total estimado</span>
          <strong>${fmtEuro(selected.effective_total_cost_eur)}</strong>
        </div>
      `;
    }

    function renderAlternativesList(alternatives) {
      if (!alternatives.length) return '';
      return alternatives.map(({ item, index }) => {
        const altStation = item.station || {};
        const altLocation = stationDetailLine(altStation);
        const subParts = [
          fmtPrice(item.price_eur_l),
          `+${fmtKm(item.extra_detour_km)}`,
          altLocation ? escapeHtml(altLocation) : '',
        ].filter(Boolean);
        return `
          <button class="rank" type="button" data-result-index="${index}">
            <div class="rank-num">${index + 1}</div>
            <div class="rank-body">
              <div class="rank-main-row">
                <span class="rank-name">${escapeHtml(altStation.name || 'Estación')}</span>
                <span class="rank-cost">${fmtEuro(item.effective_total_cost_eur)}</span>
              </div>
              <div class="rank-sub">${subParts.join(' · ')}</div>
            </div>
          </button>
        `;
      }).join('');
    }

    function emptyResultHtml(data) {
      const warningHtml = renderWarnings(data.warnings || []);
      if (warningHtml) {
        return `
          <h2>Sin resultado</h2>
          <p class="muted">No hay gasolineras candidatas con la política actual.</p>
          ${warningHtml}
        `;
      }
      const reasons = [
        'Puede faltar cobertura para ese combustible en la zona.',
        'Los filtros de marca pueden ser demasiado restrictivos.',
        'El radio o corredor de búsqueda puede no incluir gasolineras con datos válidos.',
      ];
      if ((data.brand_filter || []).length) {
        reasons.unshift('Hay filtros de marca activos.');
      }
      const items = reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join('');
      return `
        <h2>Sin resultado</h2>
        <p class="muted">No hay gasolineras candidatas con la política actual.</p>
        <ul class="muted">${items}</ul>
      `;
    }

    function setResultAlternativesState(resultElement, toggle, panel, isOpen, alternativesLabel) {
      resultElement.classList.toggle('result-panel--expanded', isOpen);
      resultElement.classList.toggle('result-panel--collapsed', !isOpen);
      toggle.setAttribute('aria-expanded', String(isOpen));
      panel.classList.toggle('collapsed', !isOpen);
      panel.setAttribute('aria-hidden', String(!isOpen));
      toggle.querySelector('.toggle-label').textContent = 'Otras alternativas';
      state.alternativesOpen = isOpen;
      refitVisibleRoute();
      refitVisibleRoute(320);
    }

    function renderResult(data, selectedIndex = 0, keepAlternativesOpen = false) {
      const resultElement = $('result');
      resultElement.removeAttribute('data-empty');
      resultElement.classList.remove('result-panel--expanded', 'result-panel--collapsed');
      if (!data.best) {
        resultElement.innerHTML = emptyResultHtml(data);
        resultElement.insertAdjacentHTML('afterbegin', resultCloseButton());
        bindResultCloseButton();
        return;
      }
      setSidebarCollapsed(true);
      state.lastOptimization = data;
      state.selectedResultIndex = selectedIndex;
      const selected = data.items[selectedIndex] || data.best || data.items[0];
      const station = selected.station;
      state.selectedStation = station;
      const saving = selected.net_savings_vs_reference_eur || 0;
      renderSelectedStationMarker(station);
      const canDrawRoute = Boolean(state.origin && state.destination && state.selectedStation);
      const alternatives = data.items
        .map((item, index) => ({ item, index }))
        .filter(row => row.index !== selectedIndex);
      const rows = renderAlternativesList(alternatives);
      const alternativesLabel = alternatives.length === 1 ? 'Ver 1 alternativa' : `Ver ${alternatives.length} alternativas`;
      const alternativesOpen = alternatives.length > 0 && keepAlternativesOpen;
      const panelClass = alternativesOpen ? 'ranking' : 'ranking collapsed';
      resultElement.classList.toggle('result-panel--expanded', alternativesOpen);
      resultElement.classList.toggle('result-panel--collapsed', !alternativesOpen);
      state.alternativesOpen = alternativesOpen;
      const whySelected = escapeHtml(selected.why_selected || 'Ordenado por menor coste efectivo total.');
      const routeNote = routeSourceNote(data, selected);
      const resultWarnings = data.warnings || [];
      const warningsHtml = renderWarnings(resultWarnings);
      const metrics = renderResultMetricRows(selected, resultWarnings, saving);
      const _savingIntensity = Math.min(Math.abs(saving), 5) / 5;
      const _savingOpacity = _savingIntensity * 0.15;
      const _savingGradient = saving === 0
        ? 'transparent'
        : `linear-gradient(to bottom, rgba(${saving > 0 ? '45,122,79' : '192,57,43'},${_savingOpacity}) 0%, transparent 100%)`;
      resultElement.innerHTML = `
        <section class="result-summary-card">
          ${resultCloseButton()}
          <div class="result-main-metric" style="background:${_savingGradient}">
            <span class="result-main-label-row">Ahorro estimado ${infoIconHtml('ahorro', 'below')}</span>
            <div class="result-main-value">
              <strong style="color:${saving > 0 ? '#2D7A4F' : saving < 0 ? '#C0392B' : '#6B6560'}">${fmtEuro(saving)}</strong>
            </div>
          </div>
          <div class="metrics result-metric-list">${metrics}</div>
        </section>
        ${routeNote}
        ${warningsHtml}
        <section class="result-alternatives">
          <button id="toggle_alternatives" class="alternatives-toggle" type="button" aria-expanded="${String(alternativesOpen)}">
            <span class="alternatives-toggle-text">
              <span class="toggle-label">Otras alternativas</span>
              <span class="toggle-sublabel">Ordenadas por coste efectivo neto</span>
            </span>
            <span class="chevron" aria-hidden="true"></span>
          </button>
          <div id="alternatives_panel" class="${panelClass}" aria-hidden="${String(!alternativesOpen)}">${rows}</div>
        </section>
      `;
      bindResultCloseButton();
      if (canDrawRoute) {
        // Remove the previous route polyline immediately (before the async
        // fetch) so the old route never overlaps the new one.
        clearCurrentRouteLayer();
        setRouteStatus('Calculando ruta...');
        refreshSelectedRoute({ fitBounds: true });
      } else {
        clearSelectedRoute();
        requestAnimationFrame(() => requestAnimationFrame(() => fitRouteToUsableViewport(null)));
      }
      state.resultHasFit = true;
      const toggle = $('toggle_alternatives');
      const panel = $('alternatives_panel');
      if (!alternatives.length) {
        toggle.disabled = true;
        toggle.querySelector('.toggle-label').textContent = 'Sin alternativas adicionales';
      } else {
        toggle.addEventListener('click', () => {
          const open = toggle.getAttribute('aria-expanded') === 'true';
          setResultAlternativesState(resultElement, toggle, panel, !open, alternativesLabel);
        });
        panel.querySelectorAll('[data-result-index]').forEach(button => {
          button.addEventListener('click', () => {
            renderResult(data, Number(button.dataset.resultIndex), true);
          });
        });
      }
    }

    async function readJsonOrError(response) {
      const text = await response.text();
      if (!text) return {};
      try {
        return JSON.parse(text);
      } catch {
        return { detail: text || response.statusText || `HTTP ${response.status}` };
      }
    }

    async function requestOptimization(payload) {
      const response = await fetch('/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await readJsonOrError(response);
      if (response.ok) return { data, fallbackUsed: false };

      const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      const orsRelated = /ors|openrouteservice|route|matrix|api[_ -]?key/i.test(detail);
      if (payload.use_ors && orsRelated && [400, 502, 503, 504].includes(response.status)) {
        const fallbackResponse = await fetch('/optimize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...payload, use_ors: false }),
        });
        const fallbackData = await readJsonOrError(fallbackResponse);
        if (fallbackResponse.ok) return { data: fallbackData, fallbackUsed: true };
        const fallbackDetail = typeof fallbackData.detail === 'string' ? fallbackData.detail : JSON.stringify(fallbackData.detail);
        throw new Error(fallbackDetail);
      }
      throw new Error(detail);
    }

    async function optimize() {
      if (!state.origin) {
        $('status').textContent = 'Selecciona una salida.';
        return;
      }
      if (!$('return_to_origin').checked && !state.destination) {
        $('status').textContent = 'Selecciona una llegada.';
        return;
      }
      const destination = $('return_to_origin').checked ? state.origin : state.destination;
      const button = $('submit');
      button.disabled = true;
      $('status').textContent = 'Calculando...';
      try {
        const amount = parsePositiveDecimal('liters');
        const consumption = parsePositiveDecimal('consumption_l_100km');
        if (amount === null) {
          $('status').textContent = state.inputMode === 'budget'
            ? 'Introduce un importe válido.'
            : 'Introduce litros válidos.';
          return;
        }
        if (consumption === null) {
          $('status').textContent = 'Introduce un consumo medio válido.';
          return;
        }
        const brands = selectedBrands();
        const excluded = excludedBrands();
        const shouldExcludeBrands = state.brandFilterMode === 'all_except' && excluded.length > 0
          || shouldUseBrandExclusions(brands, excluded);
        const shouldFilterByBrands = !shouldExcludeBrands && brands.length > 0 && !allBrandsSelected();
        if (shouldFilterByBrands && brands.length > 10) {
          $('status').textContent = 'Puedes elegir hasta 10 marcas concretas. Usa "Todas" para buscar en todo el catalogo.';
          return;
        }
        const payload = {
          origin_lat: state.origin.lat,
          origin_lon: state.origin.lon,
          destination_lat: destination.lat,
          destination_lon: destination.lon,
          fuel_type: getPddValue('fuel_type'),
          optimization_mode: getPddValue('optimization_mode'),
          input_mode: state.inputMode,
          liters: state.inputMode === 'liters' ? amount : 1,
          consumption_l_100km: consumption,
          max_search_extent_km: 150,
          economic_expansion_enabled: true,
          local_search_radius_km: 50,
          corridor_radius_km: 10,
          max_candidates: 75,
          result_limit: 10,
          use_ors: true,
        };
        if (state.inputMode === 'budget') {
          payload.budget_amount_eur = amount;
        }
        if (shouldFilterByBrands) {
          payload.brands = brands;
        }
        if (shouldExcludeBrands) {
          payload.excluded_brands = excluded;
        }
        const { data, fallbackUsed } = await requestOptimization(payload);
        state.resultHasFit = false;
        renderResult(data, 0, false);
        track('Optimización calculada', { resultados: String(data.returned), fallback: String(fallbackUsed) });
        $('status').textContent = fallbackUsed
          ? `${data.returned} alternativas evaluadas con estimación por distancia`
          : `${data.returned} alternativas evaluadas`;
      } catch (error) {
        const resultElement = $('result');
        resultElement.removeAttribute('data-empty');
        resultElement.classList.remove('result-panel--expanded', 'result-panel--collapsed');
        resultElement.innerHTML = `<h2>Error</h2><p class="error">${escapeHtml(error.message)}</p>`;
        resultElement.insertAdjacentHTML('afterbegin', resultCloseButton());
        bindResultCloseButton();
        $('status').textContent = '';
      } finally {
        button.disabled = false;
      }
    }

    initPDD('fuel_type');
    initPDD('optimization_mode');

    $('submit').addEventListener('click', optimize);
    loadCatalogStatus().then(startCatalogStatusPolling).catch(error => {
      $('refresh_status').textContent = 'Precios actualizados: --';
      $('status').textContent = error.message;
      startCatalogStatusPolling();
    });
    loadOptions().catch(error => {
      $('status').textContent = error.message;
    });
