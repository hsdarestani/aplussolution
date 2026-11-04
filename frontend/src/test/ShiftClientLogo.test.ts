import { describe, expect, it } from 'vitest';
import { resolveShiftClientBrand } from '../ShiftClientLogo';

describe('official client logos in mobile Dienstplan', () => {
  it('matches the three customer brands from the real schedule', () => {
    expect(resolveShiftClientBrand({ client_name: "Martha's finest", location_name: 'Evangelische Akademie' })).toBe('marthas');
    expect(resolveShiftClientBrand({ client_name: 'Stadthaus am Markt' })).toBe('stadthaus');
    expect(resolveShiftClientBrand({ client_name: 'Hotel Spenerhaus' })).toBe('spenerhaus');
  });

  it('falls back to plain customer text rather than inventing a logo', () => {
    expect(resolveShiftClientBrand({ client_name: 'Unbekannter Kunde', location_name: 'Frankfurt' })).toBe(null);
    expect(resolveShiftClientBrand({ client_name: '' })).toBe(null);
  });

  it('recognises the Evangelische Akademie venue only when the customer is missing', () => {
    expect(resolveShiftClientBrand({ location_name: 'Evangelische Akademie' })).toBe('marthas');
    expect(resolveShiftClientBrand({ client_name: 'Lectron GmbH', location_name: 'Stadthaus am Markt' })).toBe('stadthaus');
    expect(resolveShiftClientBrand({ client_name: 'Stadthaus Frankfurt', location_name: 'Markt 1' })).toBe('stadthaus');

    expect(resolveShiftClientBrand({ client_name: 'Anderer Kunde', location_name: 'Evangelische Akademie' })).toBe(null);
  });
});
