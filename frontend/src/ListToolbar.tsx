import React from 'react';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/react';
import './list-toolbar.css';

type Option = { value: string; label: string };

export default function ListToolbar({
  query,
  onQuery,
  placeholder = 'Liste durchsuchen …',
  status,
  onStatus,
  statusOptions = [],
  sort,
  onSort,
  sortOptions = [],
  count,
}: {
  query: string;
  onQuery: (value: string) => void;
  placeholder?: string;
  status?: string;
  onStatus?: (value: string) => void;
  statusOptions?: Option[];
  sort?: string;
  onSort?: (value: string) => void;
  sortOptions?: Option[];
  count?: number;
}) {
  return (
    <div className="list-toolbar-v4">
      <IonInput
        fill="outline"
        className="list-toolbar-search"
        placeholder={placeholder}
        value={query}
        onIonInput={(event) => onQuery(String(event.detail.value || ''))}
      />
      {onStatus && statusOptions.length > 0 && (
        <IonSelect fill="outline" interface="popover" value={status || ''} onIonChange={(event) => onStatus(String(event.detail.value || ''))} aria-label="Status filtern">
          <IonSelectOption value="">Alle Status</IonSelectOption>
          {statusOptions.map((option) => <IonSelectOption key={option.value} value={option.value}>{option.label}</IonSelectOption>)}
        </IonSelect>
      )}
      {onSort && sortOptions.length > 0 && (
        <IonSelect fill="outline" interface="popover" value={sort || ''} onIonChange={(event) => onSort(String(event.detail.value || ''))} aria-label="Sortierung">
          {sortOptions.map((option) => <IonSelectOption key={option.value} value={option.value}>{option.label}</IonSelectOption>)}
        </IonSelect>
      )}
      {typeof count === 'number' && <span className="list-toolbar-count">{count} Treffer</span>}
    </div>
  );
}
