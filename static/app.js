    const $ = (id) => document.getElementById(id);
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

    function updateCatalogDetails(catalog) {
      if (!catalog) return;
      const reasons = catalogReasons(catalog);
      const buildStatus = $('catalog_build_status');
      const referenceStatus = $('catalog_reference_status');
      const quality = $('catalog_quality_status');
      if (buildStatus) buildStatus.textContent = '';
      if (referenceStatus) referenceStatus.textContent = '';
      if (quality) {
        quality.textContent = '';
        quality.classList.toggle('degraded', false);
        quality.title = reasons.join('\n');
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
      $('refresh_status').textContent = `Precios descargados: ${stamp}`;
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
        if ($('refresh_catalog').disabled) return;
        loadCatalogStatus({ announceChange: true }).catch(() => {});
      }, 30000);
    }

    async function forceCatalogRefresh() {
      const button = $('refresh_catalog');
      button.disabled = true;
      button.classList.add('loading');
      $('refresh_status').textContent = 'Actualizando datos...';
      try {
        const response = await fetch('/catalog/refresh', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo actualizar el catálogo');
        lastCatalogStatus = data.catalog;
        updateRefreshLabel(data.catalog, 'success');
        await loadOptions();
      } catch (error) {
        $('refresh_status').textContent = 'Refresh fallido';
        $('status').textContent = error.message;
      } finally {
        button.disabled = false;
        button.classList.remove('loading');
      }
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

    function brandInputs() {
      return [...document.querySelectorAll('[name="brand_filter"]')];
    }

    function allBrandsSelected() {
      const inputs = brandInputs();
      return inputs.length > 0 && inputs.every(input => input.checked);
    }

    function updateBrandFilterState() {
      const allSelected = allBrandsSelected();
      $('select_all_brands').classList.toggle('active', allSelected);
      $('select_all_brands').setAttribute('aria-pressed', String(allSelected));
    }

    function renderBrands(brands) {
      const realBrands = brands.filter(brand => !brand.is_virtual);
      const virtualBrands = brands.filter(brand => brand.is_virtual);
      const visible = [...realBrands.slice(0, 24), ...virtualBrands];
      $('brand_checks').innerHTML = visible.map((brand) => `
        <label class="brand-check${brand.is_virtual ? ' brand-check--virtual' : ''}" title="${escapeHtml(brand.label)}">
          <span class="brand-copy">
            <strong>${escapeHtml(brand.label)}</strong>
            <small>${Number(brand.station_count || 0).toLocaleString('es-ES')} estaciones</small>
            ${brand.hint ? `<small class="brand-hint">${escapeHtml(brand.hint)}</small>` : ''}
          </span>
          <input type="checkbox" name="brand_filter" value="${escapeHtml(brand.canonical)}" checked>
          <span class="brand-toggle" aria-hidden="true"></span>
        </label>
      `).join('');
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
      userLocationMarker: null,
      userLocationAccuracyCircle: null,
    };

    const map = L.map('map', { zoomControl: false, doubleClickZoom: false }).setView([40.4168, -3.7038], 6);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
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

    function refreshMapSize() {
      setTimeout(() => map.invalidateSize({ pan: false }), 340);
    }

    function setSidebarCollapsed(collapsed) {
      state.sidebarCollapsed = Boolean(collapsed);
      const shouldCollapse = state.sidebarCollapsed && desktopSidebarQuery.matches;
      document.querySelector('.shell').classList.toggle('sidebar-collapsed', shouldCollapse);
      $('sidebar_toggle').setAttribute('aria-expanded', String(!shouldCollapse));
      $('sidebar_toggle').setAttribute('aria-label', shouldCollapse ? 'Desplegar filtros' : 'Contraer filtros');
      $('sidebar_toggle').setAttribute('title', shouldCollapse ? 'Desplegar filtros' : 'Contraer filtros');
      document.querySelectorAll('.headline, .controls, .side footer, .wordmark, .nav, .refresh-widget').forEach(element => {
        element.setAttribute('aria-hidden', String(shouldCollapse));
      });
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
            weight: 1,
            opacity: .35,
            fillColor: '#16849a',
            fillOpacity: .08,
            interactive: false,
          }).addTo(map);
        }
      } else if (state.userLocationAccuracyCircle) {
        map.removeLayer(state.userLocationAccuracyCircle);
        state.userLocationAccuracyCircle = null;
      }
      map.setView(latLng, Math.max(map.getZoom(), 15), { animate: true });
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
        options: { position: 'bottomright' },
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

    function clearSelectedRoute() {
      state.routeKey = '';
      state.routeRequestId += 1;
      setRouteStatus('');
      if (state.route) {
        map.removeLayer(state.route);
        state.route = null;
      }
    }

    function resetMapView() {
      map.setView([40.4168, -3.7038], 6);
    }

    function fitRouteLayer(layer) {
      const bounds = layer.getBounds();
      if (!bounds.isValid()) return;
      const resultVisible = $('result').getAttribute('data-empty') !== 'true';
      map.fitBounds(bounds.pad(.12), {
        animate: true,
        duration: .45,
        paddingTopLeft: [28, 96],
        paddingBottomRight: [
          desktopSidebarQuery.matches && resultVisible ? 420 : 28,
          resultVisible ? 250 : 40,
        ],
      });
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
      return point === 'origin' ? 'Sin salida seleccionada' : 'Sin llegada seleccionada';
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
      $(`${point}_choice`).textContent = label;
      if (state.active === point) {
        $('map_search').value = place ? placeDisplayLabel(place) : '';
        $('map_choice').textContent = label;
      }
    }

    function syncAllPointUI() {
      syncPointUI('origin');
      syncPointUI('destination');
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

    function resultCloseButton() {
      return '<button id="close_result" class="result-close" type="button" aria-label="Cerrar resultados" title="Cerrar resultados">×</button>';
    }

    function bindResultCloseButton() {
      const button = $('close_result');
      if (button) button.addEventListener('click', resetResultsAndMap);
    }

    function resetResultsAndMap() {
      clearSelectedRoute();
      Object.values(state.markers).forEach(marker => {
        if (marker) map.removeLayer(marker);
      });
      state.markers = {};
      state.origin = null;
      state.destination = null;
      state.selectedStation = null;
      state.lastOptimization = null;
      state.selectedResultIndex = 0;
      state.alternativesOpen = false;
      state.resultHasFit = false;
      state.focusRequestId += 1;
      state.reverseGeocodeRequestId += 1;
      const result = $('result');
      result.innerHTML = '';
      result.setAttribute('data-empty', 'true');
      $('status').textContent = '';
      clearSuggestions();
      syncAllPointUI();
      setActive('origin');
      setSidebarCollapsed(false);
      resetMapView();
    }

    function setActive(point) {
      state.active = point;
      $('tab_origin').classList.toggle('active', point === 'origin');
      $('tab_destination').classList.toggle('active', point === 'destination');
      $('map_search_label').textContent = point === 'origin' ? 'Buscar salida' : 'Buscar llegada';
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
        setPoint('destination', { ...place, label: `${place.label}` });
        return;
      }
      if (state.selectedStation && state.origin && state.destination) {
        refreshSelectedRoute({ fitBounds: true });
      } else {
        clearSelectedRoute();
        const group = Object.values(state.markers);
        if (group.length) map.fitBounds(L.featureGroup(group).getBounds().pad(.35));
      }
    }

    function clearSuggestions() {
      const box = $('map_suggestions');
      box.parentElement.style.display = 'none';
      box.innerHTML = '';
      box.style.display = 'none';
    }

    async function searchPlaces() {
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
      try {
        const center = map.getCenter();
        const url = new URL('/geocode', window.location.origin);
        url.searchParams.set('q', q);
        url.searchParams.set('size', '10');
        url.searchParams.set('focus_lat', center.lat.toFixed(6));
        url.searchParams.set('focus_lon', center.lng.toFixed(6));
        const response = await fetch(url);
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo buscar el lugar');
        if (!data.items.length) {
          box.innerHTML = '<button class="suggestion" type="button">Sin resultados</button>';
          return;
        }
        box.innerHTML = data.items.map(renderSuggestion).join('');
        [...box.querySelectorAll('[data-idx]')].forEach(button => {
          button.addEventListener('click', () => {
            setPoint(point, data.items[Number(button.dataset.idx)]);
            clearSuggestions();
          });
        });
      } catch (error) {
        box.innerHTML = `<button class="suggestion" type="button">${escapeHtml(error.message)}</button>`;
      }
    }

    let searchTimer = null;
    $('map_search').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(searchPlaces, 260);
    });

    map.on('dblclick', (event) => {
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

    function syncReturnMode() {
      const same = $('return_to_origin').checked;
      $('destination_block').style.display = same ? 'none' : 'block';
      $('tab_destination').style.display = same ? 'none' : 'block';
      if (same && state.origin) setPoint('destination', { ...state.origin });
      if (same && !state.origin) {
        state.destination = null;
        if (state.markers.destination) {
          map.removeLayer(state.markers.destination);
          state.markers.destination = null;
        }
      }
      syncAllPointUI();
      if (!same) setActive('destination');
    }

    $('tab_origin').addEventListener('click', () => setActive('origin'));
    $('tab_destination').addEventListener('click', () => setActive('destination'));
    $('return_to_origin').addEventListener('change', syncReturnMode);
    $('sidebar_toggle').addEventListener('click', () => setSidebarCollapsed(!state.sidebarCollapsed));
    desktopSidebarQuery.addEventListener('change', () => setSidebarCollapsed(state.sidebarCollapsed));
    $('refresh_catalog').addEventListener('click', forceCatalogRefresh);
    $('refill_mode_liters').addEventListener('click', () => setInputMode('liters'));
    $('refill_mode_budget').addEventListener('click', () => setInputMode('budget'));

    syncRefuelInputUI();
    syncAllPointUI();
    setActive('origin');
    syncReturnMode();

    async function loadOptions() {
      const [fuels, brands] = await Promise.all([
        fetch('/fuels').then(r => r.json()),
        fetch('/brands').then(r => r.json()),
      ]);
      $('fuel_type').innerHTML = fuels.fuels
        .map(f => `<option value="${escapeHtml(f.key)}">${escapeHtml(f.label)}</option>`)
        .join('');
      renderBrands(brands.brands || []);
    }

    $('select_all_brands').addEventListener('click', () => {
      const shouldSelectAll = !allBrandsSelected();
      brandInputs().forEach(input => {
        input.checked = shouldSelectAll;
      });
      $('status').textContent = '';
      updateBrandFilterState();
    });

    $('brand_checks').addEventListener('change', (event) => {
      const input = event.target;
      if (!input.matches('[name="brand_filter"]')) return;
      if (input.checked && selectedBrands().length > 10 && !allBrandsSelected()) {
        input.checked = !input.checked;
        $('status').textContent = '';
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
        <span class="price-warning" tabindex="0" aria-label="${escapeHtml(warningTitle)}">
          <span class="price-warning-icon" aria-hidden="true"></span>
          <span class="price-warning-tooltip" role="tooltip">
            <strong>${escapeHtml(warningTitle)}</strong>
            <span>${escapeHtml(warningCopy)}</span>
          </span>
        </span>
      ` : '';
      return `
        <div class="metric metric--price">
          <span>Precio</span>
          <strong>${fmtPrice(price)}</strong>
          ${priceWarning}
        </div>
      `;
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

    function renderResult(data, selectedIndex = 0, keepAlternativesOpen = false) {
      $('result').removeAttribute('data-empty');
      if (!data.best) {
        $('result').innerHTML = emptyResultHtml(data);
        $('result').insertAdjacentHTML('afterbegin', resultCloseButton());
        bindResultCloseButton();
        return;
      }
      setSidebarCollapsed(true);
      state.lastOptimization = data;
      state.selectedResultIndex = selectedIndex;
      state.alternativesOpen = keepAlternativesOpen;
      const selected = data.items[selectedIndex] || data.best || data.items[0];
      const station = selected.station;
      state.selectedStation = station;
      const saving = selected.net_savings_vs_reference_eur || 0;
      const isBudgetMode = selected.input_mode === 'budget';
      const budget = candidateBudget(selected);
      const grossLiters = candidateGrossLiters(selected);
      const litersDelta = Number(selected.net_liters_vs_reference || 0);
      renderSelectedStationMarker(station);
      const canDrawRoute = Boolean(state.origin && state.destination && state.selectedStation);
      scheduleStationFocus(station, 0);
      refreshSelectedRoute({ fitBounds: true });
      const alternatives = data.items
        .map((item, index) => ({ item, index }))
        .filter(row => row.index !== selectedIndex);
      const rows = alternatives.map(({ item, index }) => {
        const altStation = item.station || {};
        const altBudget = candidateBudget(item);
        const altDetail = item.input_mode === 'budget' && altBudget
          ? `${fmtLiters(candidateGrossLiters(item))} por ${fmtEuro(altBudget)}`
          : fmtEuro(item.effective_total_cost_eur);
        return `
          <button class="rank" type="button" data-result-index="${index}">
            <div class="rank-num">${index + 1}</div>
            <div>
              <strong>${escapeHtml(altStation.name)}</strong><br>
              <span class="muted">${escapeHtml(altStation.brand_canonical)} · ${fmtKm(item.extra_detour_km)}</span>
            </div>
            <div class="rank-price">${fmtPrice(item.price_eur_l)}<br><span class="muted">${altDetail}</span></div>
          </button>
        `;
      }).join('');
      const alternativesLabel = alternatives.length === 1 ? 'Ver 1 alternativa' : `Ver ${alternatives.length} alternativas`;
      const panelClass = keepAlternativesOpen ? 'ranking' : 'ranking collapsed';
      const stationName = escapeHtml(station.name);
      const stationLocation = [station.address, station.municipality].filter(Boolean).map(escapeHtml).join(' · ');
      const whySelected = escapeHtml(selected.why_selected || 'Ordenado por menor coste efectivo total.');
      const routeNote = routeSourceNote(data, selected);
      const resultWarnings = data.warnings || [];
      const warningsHtml = renderWarnings(resultWarnings);
      const priceMetric = priceMetricHtml(selected.price_eur_l, resultWarnings);
      const metrics = isBudgetMode
        ? `
          ${priceMetric}
          <div class="metric"><span>Presupuesto</span><strong>${fmtEuro(budget || 0)}</strong></div>
          <div class="metric saving"><span>Litros aprox.</span><strong>${fmtLiters(grossLiters)}</strong></div>
          <div class="metric"><span>Diferencia neta</span><strong>${litersDelta >= 0 ? '+' : ''}${fmtLiters(litersDelta)}</strong></div>
        `
        : `
          ${priceMetric}
          <div class="metric"><span>Coste efectivo</span><strong>${fmtEuro(selected.effective_total_cost_eur)}</strong></div>
          <div class="metric saving"><span>Ahorro neto</span><strong>${saving >= 0 ? fmtEuro(saving) : '-' + fmtEuro(Math.abs(saving))}</strong></div>
          <div class="metric"><span>Desvío extra</span><strong>${fmtKm(selected.extra_detour_km)}</strong></div>
        `;
      const amountSummary = isBudgetMode && budget
        ? `<p class="muted">Con ${fmtEuro(budget)}, aquí repostarías aproximadamente ${fmtLiters(grossLiters)}.</p>`
        : '';
      $('result').innerHTML = `
        <h2>${stationName}</h2>
        <p class="muted">${stationLocation}</p>
        <div class="metrics">${metrics}</div>
        <p class="muted">${whySelected}</p>
        ${routeNote}
        ${warningsHtml}
        <button id="toggle_alternatives" class="alternatives-toggle" type="button" aria-expanded="${String(keepAlternativesOpen)}">
          <span class="toggle-label">${keepAlternativesOpen ? 'Ocultar alternativas' : alternativesLabel}</span>
          <span class="chevron" aria-hidden="true"></span>
        </button>
        <div id="alternatives_panel" class="${panelClass}" aria-hidden="${String(!keepAlternativesOpen)}">${rows}</div>
      `;
      if (amountSummary) $('result').querySelector('.metrics').insertAdjacentHTML('afterend', amountSummary);
      $('result').insertAdjacentHTML('afterbegin', resultCloseButton());
      bindResultCloseButton();
      if (!canDrawRoute) scheduleStationFocus(station, state.resultHasFit ? 0 : 360);
      state.resultHasFit = true;
      const toggle = $('toggle_alternatives');
      const panel = $('alternatives_panel');
      if (!alternatives.length) {
        toggle.disabled = true;
        toggle.querySelector('.toggle-label').textContent = 'Sin alternativas adicionales';
      } else {
        toggle.addEventListener('click', () => {
          const open = toggle.getAttribute('aria-expanded') === 'true';
          toggle.setAttribute('aria-expanded', String(!open));
          panel.classList.toggle('collapsed', open);
          panel.setAttribute('aria-hidden', String(open));
          toggle.querySelector('.toggle-label').textContent = open ? alternativesLabel : 'Ocultar alternativas';
          state.alternativesOpen = !open;
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
        const shouldFilterByBrands = brands.length > 0 && !allBrandsSelected();
        const payload = {
          origin_lat: state.origin.lat,
          origin_lon: state.origin.lon,
          destination_lat: destination.lat,
          destination_lon: destination.lon,
          fuel_type: $('fuel_type').value,
          optimization_mode: $('optimization_mode').value,
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
        const { data, fallbackUsed } = await requestOptimization(payload);
        state.resultHasFit = false;
        renderResult(data, 0, false);
        $('status').textContent = fallbackUsed
          ? `${data.returned} alternativas evaluadas con estimación por distancia`
          : `${data.returned} alternativas evaluadas`;
      } catch (error) {
        $('result').removeAttribute('data-empty');
        $('result').innerHTML = `<h2>Error</h2><p class="error">${escapeHtml(error.message)}</p>`;
        $('result').insertAdjacentHTML('afterbegin', resultCloseButton());
        bindResultCloseButton();
        $('status').textContent = '';
      } finally {
        button.disabled = false;
      }
    }

    $('submit').addEventListener('click', optimize);
    loadCatalogStatus().then(startCatalogStatusPolling).catch(error => {
      $('refresh_status').textContent = 'Último refresh: --';
      $('status').textContent = error.message;
      startCatalogStatusPolling();
    });
    loadOptions().catch(error => {
      $('status').textContent = error.message;
    });
