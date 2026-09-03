import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';

type ClientRow = { id: string; name: string };
type LocationRow = { id: string; name: string; client: string };

const unpack = (value: any): any[] => value?.results || value || [];
const same = (left: string[], right: string[]) => left.length === right.length && left.every((value, index) => value === right[index]);

function selectedClientNamesFromPdf(): string[] {
  const blocks = Array.from(document.querySelectorAll<HTMLElement>('.wiw-pdf-filter-block'));
  const clientBlock = blocks.find((block) => block.querySelector('b')?.textContent?.trim() === 'Kunden');
  if (!clientBlock) return [];
  return Array.from(clientBlock.querySelectorAll<HTMLButtonElement>('button.active'))
    .map((button) => button.textContent?.trim() || '')
    .filter((label) => label && label !== 'Alle Kunden');
}

export default function SchedulePdfLocationFilter() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [locations, setLocations] = useState<LocationRow[]>([]);
  const [selectedClientIds, setSelectedClientIds] = useState<string[]>([]);
  const [selectedLocations, setSelectedLocations] = useState<string[]>([]);
  const selectedLocationsRef = useRef<string[]>([]);
  const loadStarted = useRef(false);

  const setLocationSelection = (next: string[]) => {
    selectedLocationsRef.current = next;
    setSelectedLocations(next);
  };

  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const wrappedFetch: typeof window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const chosen = selectedLocationsRef.current;
      if (!chosen.length) return previousFetch(input, init);
      try {
        const rawUrl = typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
        if (!rawUrl.includes('/api/reports/schedule.pdf')) return previousFetch(input, init);
        const url = new URL(rawUrl, window.location.origin);
        url.searchParams.set('locations', chosen.join(','));
        if (typeof input === 'string' || input instanceof URL) {
          return previousFetch(url.toString(), init);
        }
        return previousFetch(new Request(url.toString(), input), init);
      } catch {
        return previousFetch(input, init);
      }
    }) as typeof window.fetch;

    window.fetch = wrappedFetch;
    return () => {
      if (window.fetch === wrappedFetch) window.fetch = previousFetch;
    };
  }, []);

  useEffect(() => {
    let disposed = false;

    const loadMeta = async () => {
      if (loadStarted.current) return;
      loadStarted.current = true;
      try {
        const [clientData, locationData] = await Promise.all([
          api('clients/?page_size=500'),
          api('locations/?page_size=500'),
        ]);
        if (disposed) return;
        setClients(unpack(clientData).map((item: any) => ({ id: String(item.id), name: String(item.name || '') })));
        setLocations(unpack(locationData).map((item: any) => ({ id: String(item.id), name: String(item.name || ''), client: String(item.client || '') })));
      } catch {
        loadStarted.current = false;
      }
    };

    const sync = () => {
      const scroll = document.querySelector<HTMLElement>('.wiw-pdf-scroll');
      if (!scroll) {
        setHost(null);
        setSelectedClientIds((current) => current.length ? [] : current);
        if (selectedLocationsRef.current.length) setLocationSelection([]);
        return;
      }

      void loadMeta();
      const blocks = Array.from(scroll.querySelectorAll<HTMLElement>('.wiw-pdf-filter-block'));
      const clientBlock = blocks.find((block) => block.querySelector('b')?.textContent?.trim() === 'Kunden');
      if (!clientBlock) return;

      let portalHost = scroll.querySelector<HTMLElement>('#wiw-pdf-location-filter-host');
      if (!portalHost) {
        portalHost = document.createElement('div');
        portalHost.id = 'wiw-pdf-location-filter-host';
        clientBlock.insertAdjacentElement('afterend', portalHost);
      }
      setHost((current) => current === portalHost ? current : portalHost);

      if (!clients.length) return;
      const names = selectedClientNamesFromPdf();
      const nextIds = clients
        .filter((client) => names.includes(client.name))
        .map((client) => client.id)
        .sort();
      setSelectedClientIds((current) => same(current, nextIds) ? current : nextIds);
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'aria-pressed'],
    });
    return () => {
      disposed = true;
      observer.disconnect();
    };
  }, [clients.length]);

  const relevantLocations = useMemo(() => {
    if (!selectedClientIds.length) return [];
    const selected = new Set(selectedClientIds);
    return locations
      .filter((location) => selected.has(location.client))
      .sort((left, right) => left.name.localeCompare(right.name, 'de', { sensitivity: 'base' }));
  }, [locations, selectedClientIds]);

  useEffect(() => {
    const allowed = new Set(relevantLocations.map((location) => location.id));
    const next = selectedLocationsRef.current.filter((id) => allowed.has(id));
    if (!same(next, selectedLocationsRef.current)) setLocationSelection(next);
  }, [relevantLocations]);

  if (!host || relevantLocations.length <= 1) return null;

  const multipleClients = selectedClientIds.length > 1;
  const clientNames = new Map(clients.map((client) => [client.id, client.name]));

  return createPortal(
    <div className="wiw-pdf-filter-block" data-testid="pdf-location-filter">
      <b>Standorte</b>
      <div className="wiw-pdf-chip-grid">
        <button
          type="button"
          aria-pressed={selectedLocations.length === 0}
          className={selectedLocations.length === 0 ? 'active' : ''}
          onClick={() => setLocationSelection([])}
        >
          Alle Standorte
        </button>
        {relevantLocations.map((location) => {
          const active = selectedLocations.includes(location.id);
          const label = multipleClients
            ? `${clientNames.get(location.client) || 'Kunde'} · ${location.name}`
            : location.name;
          return (
            <button
              type="button"
              key={location.id}
              aria-pressed={active}
              className={active ? 'active' : ''}
              onClick={() => {
                const next = active
                  ? selectedLocations.filter((id) => id !== location.id)
                  : [...selectedLocations, location.id];
                setLocationSelection(next);
              }}
            >
              {label}
            </button>
          );
        })}
      </div>
      <small>Nichts ausgewählt = alle Standorte der gewählten Kunden</small>
    </div>,
    host,
  );
}
