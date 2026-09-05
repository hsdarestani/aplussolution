import { describe, expect, it } from 'vitest';
import { schedulePalette } from '../scheduleClientPalette';

describe('fixed schedule customer colors', () => {
  it('keeps every Martha client variant amber yellow', () => {
    expect(schedulePalette('(2) Marthas', 'Servicekraft', 275).accent).toBe('#FFBF00');
    expect(schedulePalette('Marthas Finest', 'Servicekraft', 120).accent).toBe('#FFBF00');
    expect(schedulePalette("Martha's Finest", 'Servicekraft', null).accent).toBe('#FFBF00');
  });

  it('forces Messe, OMMIA/OMNIA and Hofgut to white even with historic manual hues', () => {
    expect(schedulePalette('Messe Frankfurt', 'Servicekraft', 46).accent).toBe('#FFFFFF');
    expect(schedulePalette('Messe Frankfurt - Accente', 'Servicekraft', 46).accent).toBe('#FFFFFF');
    expect(schedulePalette('OMMIA Frankfurt', 'Servicekraft', 282).accent).toBe('#FFFFFF');
    expect(schedulePalette('Omnia Frankfurt', 'Servicekraft', 282).accent).toBe('#FFFFFF');
    expect(schedulePalette('Hofgut', 'Servicekraft', 320).accent).toBe('#FFFFFF');
    expect(schedulePalette('Hofgut Wiesenmühle GmbH', 'Servicekraft', 320).accent).toBe('#FFFFFF');
  });
});
