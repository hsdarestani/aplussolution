const BUSINESS_TIME_ZONE = 'Europe/Berlin';
const PATCH_FLAG = Symbol.for('aplus.berlin-locale-patched');

function includesGermanLocale(locales?: Intl.LocalesArgument): boolean {
  if (!locales) return false;
  if (typeof locales === 'string') return locales.toLowerCase().startsWith('de');
  try {
    return Array.from(locales as Iterable<string>).some((locale) => String(locale).toLowerCase().startsWith('de'));
  } catch {
    return false;
  }
}

function berlinOptions(locales: Intl.LocalesArgument | undefined, options?: Intl.DateTimeFormatOptions) {
  if (!includesGermanLocale(locales) || options?.timeZone) return options;
  return { ...(options || {}), timeZone: BUSINESS_TIME_ZONE };
}

export function installBerlinLocaleDefaults() {
  const proto = Date.prototype as Date & Record<PropertyKey, unknown>;
  if (proto[PATCH_FLAG]) return;

  const originalDateTime = Date.prototype.toLocaleString;
  const originalDate = Date.prototype.toLocaleDateString;
  const originalTime = Date.prototype.toLocaleTimeString;

  Object.defineProperty(Date.prototype, 'toLocaleString', {
    configurable: true,
    writable: true,
    value: function toLocaleString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return originalDateTime.call(this, locales as any, berlinOptions(locales, options));
    },
  });
  Object.defineProperty(Date.prototype, 'toLocaleDateString', {
    configurable: true,
    writable: true,
    value: function toLocaleDateString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return originalDate.call(this, locales as any, berlinOptions(locales, options));
    },
  });
  Object.defineProperty(Date.prototype, 'toLocaleTimeString', {
    configurable: true,
    writable: true,
    value: function toLocaleTimeString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return originalTime.call(this, locales as any, berlinOptions(locales, options));
    },
  });
  Object.defineProperty(Date.prototype, PATCH_FLAG, {
    configurable: false,
    enumerable: false,
    writable: false,
    value: true,
  });
}

export { BUSINESS_TIME_ZONE };
