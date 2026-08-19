type PickedLocation = {
  latitude: number;
  longitude: number;
  address?: string;
  accuracy?: number;
};

type PhotonFeature = {
  geometry?: { coordinates?: [number, number] };
  properties?: Record<string, any>;
};

let pickedLocation: PickedLocation | null = null;
let activeModal: Element | null = null;
let actionBar: HTMLDivElement | null = null;
let suggestionsPanel: HTMLDivElement | null = null;
let mapOverlay: HTMLDivElement | null = null;
let addressField: any = null;
let addressTimer = 0;
let searchController: AbortController | null = null;
let observer: MutationObserver | null = null;
let settingAddress = false;

const PHOTON = 'https://photon.komoot.io';
const DEFAULT_CENTER: [number, number] = [50.1109, 8.6821];

function ensureStyles() {
  if (document.getElementById('aplus-location-picker-style')) return;
  const style = document.createElement('style');
  style.id = 'aplus-location-picker-style';
  style.textContent = `
    .aplus-location-actions{position:fixed;z-index:31000;display:flex;gap:6px;align-items:center}
    .aplus-location-action{border:1px solid #c8d1e0;background:#fff;border-radius:9px;padding:7px 9px;font:600 12px/1 system-ui,-apple-system,sans-serif;box-shadow:0 3px 12px rgba(15,23,42,.12);cursor:pointer;white-space:nowrap}
    .aplus-location-action:disabled{opacity:.55;cursor:wait}
    .aplus-location-suggestions{position:fixed;z-index:32000;background:#fff;border:1px solid #d5dbe7;border-radius:12px;box-shadow:0 16px 40px rgba(15,23,42,.18);overflow:hidden;max-height:280px;overflow-y:auto}
    .aplus-location-suggestion{display:block;width:100%;border:0;border-bottom:1px solid #eef1f6;background:#fff;padding:11px 13px;text-align:left;font:500 13px/1.35 system-ui,-apple-system,sans-serif;cursor:pointer}
    .aplus-location-suggestion:last-child{border-bottom:0}
    .aplus-location-suggestion:hover,.aplus-location-suggestion:focus{background:#f4f7fb;outline:none}
    .aplus-map-overlay{position:fixed;inset:0;z-index:50000;background:#fff;display:flex;flex-direction:column;font-family:system-ui,-apple-system,sans-serif}
    .aplus-map-head,.aplus-map-foot{display:flex;align-items:center;gap:10px;padding:12px 14px;background:#fff;box-shadow:0 1px 0 rgba(15,23,42,.1);z-index:2}
    .aplus-map-head{justify-content:space-between}.aplus-map-foot{justify-content:space-between;box-shadow:0 -1px 0 rgba(15,23,42,.1)}
    .aplus-map-head strong{font-size:16px}.aplus-map-head small,.aplus-map-foot small{display:block;color:#667085;margin-top:2px}
    .aplus-map-button{border:1px solid #c8d1e0;background:#fff;border-radius:10px;padding:10px 13px;font-weight:650;cursor:pointer}
    .aplus-map-button.primary{background:#155eef;color:#fff;border-color:#155eef}
    .aplus-map-canvas{flex:1;min-height:280px;background:#e9eef5}
    .aplus-map-coords{font:600 12px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;color:#344054}
    @media (max-width:600px){.aplus-location-action{padding:7px 8px;font-size:11px}.aplus-map-head,.aplus-map-foot{padding:10px}.aplus-map-foot{align-items:flex-end}}
  `;
  document.head.appendChild(style);
}

function findLocationModal(): Element | null {
  return [...document.querySelectorAll('ion-modal')].find((modal) =>
    [...modal.querySelectorAll('h2')].some((heading) => heading.textContent?.trim() === 'Einsatzort anlegen'),
  ) || null;
}

function findAddressField(modal: Element): any {
  return [...modal.querySelectorAll('ion-textarea')].find((field: any) => {
    const label = String(field.label || field.getAttribute('label') || '');
    return label.startsWith('Adresse');
  }) || null;
}

function setAddress(value: string) {
  if (!addressField || !value) return;
  settingAddress = true;
  addressField.value = value;
  addressField.dispatchEvent(new CustomEvent('ionInput', { detail: { value }, bubbles: true, composed: true }));
  addressField.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true, composed: true }));
  window.setTimeout(() => { settingAddress = false; }, 0);
}

function currentAddressValue(): string {
  return String(addressField?.value || '').trim();
}

function formatAddress(feature: PhotonFeature): string {
  const p = feature.properties || {};
  const first = [p.street, p.housenumber].filter(Boolean).join(' ').trim();
  const place = p.city || p.town || p.village || p.district || p.county;
  const second = [p.postcode, place].filter(Boolean).join(' ').trim();
  const parts = [first || p.name, second, p.state, p.country].filter(Boolean);
  return [...new Set(parts.map((part) => String(part).trim()).filter(Boolean))].join(', ');
}

async function photonSearch(query: string, limit = 5): Promise<PhotonFeature[]> {
  const text = query.trim();
  if (!text) return [];
  const response = await fetch(`${PHOTON}/api/?q=${encodeURIComponent(text)}&limit=${limit}&lang=de`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error('Adresssuche ist momentan nicht erreichbar.');
  const data = await response.json();
  return Array.isArray(data?.features) ? data.features : [];
}

async function reverseGeocode(latitude: number, longitude: number): Promise<string> {
  try {
    const response = await fetch(`${PHOTON}/reverse?lat=${latitude}&lon=${longitude}&lang=de&limit=1`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return '';
    const data = await response.json();
    return formatAddress(data?.features?.[0] || {});
  } catch {
    return '';
  }
}

function featureLocation(feature: PhotonFeature): PickedLocation | null {
  const coords = feature.geometry?.coordinates;
  if (!coords || coords.length < 2) return null;
  const [longitude, latitude] = coords;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  return { latitude, longitude, address: formatAddress(feature) };
}

function clearSuggestions() {
  suggestionsPanel?.remove();
  suggestionsPanel = null;
}

function positionFloatingUi() {
  if (!addressField || !actionBar) return;
  const rect = addressField.getBoundingClientRect();
  if (!rect.width || rect.bottom < 0 || rect.top > window.innerHeight) {
    actionBar.style.display = 'none';
    clearSuggestions();
    return;
  }
  actionBar.style.display = 'flex';
  actionBar.style.top = `${Math.max(4, rect.top + 7)}px`;
  actionBar.style.right = `${Math.max(8, window.innerWidth - rect.right + 8)}px`;
  if (suggestionsPanel) {
    suggestionsPanel.style.left = `${Math.max(8, rect.left)}px`;
    suggestionsPanel.style.top = `${Math.min(window.innerHeight - 80, rect.bottom + 4)}px`;
    suggestionsPanel.style.width = `${Math.min(rect.width, window.innerWidth - 16)}px`;
  }
}

function renderSuggestions(features: PhotonFeature[]) {
  clearSuggestions();
  if (!features.length || !addressField) return;
  const panel = document.createElement('div');
  panel.className = 'aplus-location-suggestions';
  for (const feature of features) {
    const location = featureLocation(feature);
    if (!location) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'aplus-location-suggestion';
    button.textContent = location.address || `${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`;
    button.addEventListener('click', () => {
      pickedLocation = location;
      if (location.address) setAddress(location.address);
      clearSuggestions();
    });
    panel.appendChild(button);
  }
  if (!panel.childElementCount) return;
  document.body.appendChild(panel);
  suggestionsPanel = panel;
  positionFloatingUi();
}

function handleAddressInput(event: Event) {
  if (settingAddress) return;
  pickedLocation = null;
  const value = String((event as CustomEvent).detail?.value ?? addressField?.value ?? '').trim();
  window.clearTimeout(addressTimer);
  searchController?.abort();
  clearSuggestions();
  if (value.length < 3) return;
  addressTimer = window.setTimeout(async () => {
    searchController = new AbortController();
    try {
      const response = await fetch(`${PHOTON}/api/?q=${encodeURIComponent(value)}&limit=5&lang=de`, {
        signal: searchController.signal,
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) return;
      const data = await response.json();
      renderSuggestions(Array.isArray(data?.features) ? data.features : []);
    } catch (error: any) {
      if (error?.name !== 'AbortError') clearSuggestions();
    }
  }, 350);
}

function geolocationAttempt(options: PositionOptions): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, options));
}

async function getCurrentLocation(): Promise<PickedLocation> {
  if (!navigator.geolocation) throw new Error('Dieses Gerät unterstützt keine Standortbestimmung.');
  let position: GeolocationPosition;
  try {
    position = await geolocationAttempt({ enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
  } catch (firstError: any) {
    if (firstError?.code === 1) {
      throw new Error('Standortzugriff wurde blockiert. Bitte Standortberechtigung für solution.smarbiz.sbs aktivieren.');
    }
    try {
      position = await geolocationAttempt({ enableHighAccuracy: true, timeout: 25000, maximumAge: 600000 });
    } catch (secondError: any) {
      if (secondError?.code === 1) {
        throw new Error('Standortzugriff wurde blockiert. Bitte Standortberechtigung für solution.smarbiz.sbs aktivieren.');
      }
      throw new Error('GPS konnte den Standort nicht bestimmen. Bitte Adresse auswählen oder den Punkt direkt auf der Karte setzen.');
    }
  }
  const result: PickedLocation = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: position.coords.accuracy,
  };
  result.address = await reverseGeocode(result.latitude, result.longitude);
  return result;
}

function loadLeaflet(): Promise<any> {
  if ((window as any).L) return Promise.resolve((window as any).L);
  return new Promise((resolve, reject) => {
    if (!document.getElementById('aplus-leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'aplus-leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      link.integrity = 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=';
      link.crossOrigin = '';
      document.head.appendChild(link);
    }
    const existing = document.getElementById('aplus-leaflet-js') as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener('load', () => resolve((window as any).L), { once: true });
      existing.addEventListener('error', () => reject(new Error('Karte konnte nicht geladen werden.')), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.id = 'aplus-leaflet-js';
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.integrity = 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=';
    script.crossOrigin = '';
    script.onload = () => resolve((window as any).L);
    script.onerror = () => reject(new Error('Karte konnte nicht geladen werden.'));
    document.head.appendChild(script);
  });
}

async function initialMapCenter(): Promise<[number, number]> {
  if (pickedLocation) return [pickedLocation.latitude, pickedLocation.longitude];
  const query = currentAddressValue();
  if (query.length >= 3) {
    try {
      const first = featureLocation((await photonSearch(query, 1))[0]);
      if (first) {
        pickedLocation = first;
        return [first.latitude, first.longitude];
      }
    } catch {
      // Fall back to Germany/Frankfurt if address lookup is unavailable.
    }
  }
  return DEFAULT_CENTER;
}

async function openMap() {
  closeMap();
  ensureStyles();
  const overlay = document.createElement('div');
  overlay.className = 'aplus-map-overlay';
  overlay.innerHTML = `
    <div class="aplus-map-head">
      <div><strong>Standort auf Karte wählen</strong><small>Auf die genaue Position tippen.</small></div>
      <button type="button" class="aplus-map-button" data-close>Schließen</button>
    </div>
    <div class="aplus-map-canvas"></div>
    <div class="aplus-map-foot">
      <div><div class="aplus-map-coords" data-coords>Noch kein Punkt gewählt</div><small data-address>Adresse wird automatisch ermittelt.</small></div>
      <button type="button" class="aplus-map-button primary" data-accept disabled>Übernehmen</button>
    </div>`;
  document.body.appendChild(overlay);
  mapOverlay = overlay;
  overlay.querySelector('[data-close]')?.addEventListener('click', closeMap);

  try {
    const L = await loadLeaflet();
    const mapElement = overlay.querySelector('.aplus-map-canvas') as HTMLElement;
    const [latitude, longitude] = await initialMapCenter();
    const map = L.map(mapElement, { zoomControl: true }).setView([latitude, longitude], pickedLocation ? 17 : 13);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    let marker: any = null;
    let circle: any = null;
    const coordsEl = overlay.querySelector('[data-coords]') as HTMLElement;
    const addressEl = overlay.querySelector('[data-address]') as HTMLElement;
    const accept = overlay.querySelector('[data-accept]') as HTMLButtonElement;

    const radiusValue = () => {
      const modal = findLocationModal();
      const radiusField: any = modal ? [...modal.querySelectorAll('ion-input')].find((field: any) => String(field.label || field.getAttribute('label') || '').startsWith('Geofence-Radius')) : null;
      return Math.max(25, Number(radiusField?.value || 250));
    };

    const select = async (lat: number, lng: number) => {
      pickedLocation = { latitude: lat, longitude: lng };
      if (marker) marker.setLatLng([lat, lng]); else marker = L.marker([lat, lng]).addTo(map);
      if (circle) circle.setLatLng([lat, lng]).setRadius(radiusValue());
      else circle = L.circle([lat, lng], { radius: radiusValue(), weight: 2, fillOpacity: 0.08 }).addTo(map);
      coordsEl.textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)} · Radius ${radiusValue()} m`;
      addressEl.textContent = 'Adresse wird ermittelt …';
      accept.disabled = false;
      const resolved = await reverseGeocode(lat, lng);
      if (pickedLocation && Math.abs(pickedLocation.latitude - lat) < 0.000001 && Math.abs(pickedLocation.longitude - lng) < 0.000001) {
        pickedLocation.address = resolved || currentAddressValue();
        addressEl.textContent = pickedLocation.address || 'Punkt gewählt';
      }
    };

    if (pickedLocation) await select(pickedLocation.latitude, pickedLocation.longitude);
    map.on('click', (event: any) => void select(event.latlng.lat, event.latlng.lng));
    accept.addEventListener('click', () => {
      if (pickedLocation?.address) setAddress(pickedLocation.address);
      closeMap();
    });
    window.setTimeout(() => map.invalidateSize(), 50);
  } catch (error: any) {
    closeMap();
    window.alert(error?.message || 'Karte konnte nicht geöffnet werden.');
  }
}

function closeMap() {
  mapOverlay?.remove();
  mapOverlay = null;
}

async function useCurrentLocation(button: HTMLButtonElement) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = 'Ortung …';
  try {
    const location = await getCurrentLocation();
    pickedLocation = location;
    if (location.address) setAddress(location.address);
  } catch (error: any) {
    window.alert(error?.message || 'Standort konnte nicht bestimmt werden.');
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function removeEnhancer() {
  actionBar?.remove();
  actionBar = null;
  clearSuggestions();
  closeMap();
  if (addressField) addressField.removeEventListener('ionInput', handleAddressInput as EventListener);
  addressField = null;
  pickedLocation = null;
  activeModal = null;
}

function enhanceModal(modal: Element) {
  if (activeModal === modal && actionBar?.isConnected) {
    positionFloatingUi();
    return;
  }
  removeEnhancer();
  ensureStyles();
  activeModal = modal;
  addressField = findAddressField(modal);
  if (!addressField) return;
  addressField.addEventListener('ionInput', handleAddressInput as EventListener);

  const bar = document.createElement('div');
  bar.className = 'aplus-location-actions';
  const current = document.createElement('button');
  current.type = 'button';
  current.className = 'aplus-location-action';
  current.textContent = '📍 Mein Standort';
  current.addEventListener('click', () => void useCurrentLocation(current));
  const map = document.createElement('button');
  map.type = 'button';
  map.className = 'aplus-location-action';
  map.textContent = '🗺️ Karte';
  map.addEventListener('click', () => void openMap());
  bar.append(current, map);
  document.body.appendChild(bar);
  actionBar = bar;
  positionFloatingUi();
}

function scan() {
  const modal = findLocationModal();
  if (!modal) {
    if (activeModal) removeEnhancer();
    return;
  }
  enhanceModal(modal);
}

export function installLocationPicker() {
  if (typeof document === 'undefined' || observer) return;
  const start = () => {
    scan();
    observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
    window.addEventListener('resize', positionFloatingUi);
    document.addEventListener('scroll', positionFloatingUi, true);
    document.addEventListener('pointerdown', (event) => {
      const target = event.target as Node;
      if (suggestionsPanel && !suggestionsPanel.contains(target) && target !== addressField) clearSuggestions();
    }, true);
  };
  if (document.body) start(); else window.addEventListener('DOMContentLoaded', start, { once: true });
}

export async function enrichLocationPayload(payload: any): Promise<any> {
  const next = { ...payload, geofence_radius_m: Number(payload.geofence_radius_m || 250) };
  if (next.latitude != null && next.longitude != null) return next;

  if (!pickedLocation) {
    const query = String(next.address || '').trim();
    if (query.length < 3) throw new Error('Bitte eine Adresse eingeben oder den Standort auf der Karte wählen.');
    let feature: PhotonFeature | undefined;
    try {
      feature = (await photonSearch(query, 1))[0];
    } catch {
      throw new Error('Adresse konnte nicht automatisch bestimmt werden. Bitte einen Vorschlag wählen oder den Punkt auf der Karte setzen.');
    }
    pickedLocation = featureLocation(feature || {});
    if (!pickedLocation) throw new Error('Adresse wurde nicht eindeutig gefunden. Bitte einen Vorschlag wählen oder den Punkt auf der Karte setzen.');
  }

  next.latitude = pickedLocation.latitude.toFixed(6);
  next.longitude = pickedLocation.longitude.toFixed(6);
  if (pickedLocation.address) next.address = pickedLocation.address;
  return next;
}
