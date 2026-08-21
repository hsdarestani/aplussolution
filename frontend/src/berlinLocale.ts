const BUSINESS_TIME_ZONE = 'Europe/Berlin';
const PATCH_FLAG = Symbol.for('aplus.berlin-locale-patched');

function includesGermanLocale(locales?: Intl.LocalesArgument): boolean {
  if (!locales) return false;
  const values = Array.isArray(locales) ? locales : [locales];
  return values.some((locale) => String(locale).toLowerCase().startsWith('de'));
}

function berlinOptions(locales: Intl.LocalesArgument | undefined, options?: Intl.DateTimeFormatOptions) {
  if (!includesGermanLocale(locales) || options?.timeZone) return options;
  return { ...(options || {}), timeZone: BUSINESS_TIME_ZONE };
}

export function installBerlinLocaleDefaults() {
  const proto = Date.prototype as any;
  if (proto[PATCH_FLAG]) return;

  const originalDateTime = Date.prototype.toLocaleString;
  const originalDate = Date.prototype.toLocaleDateString;
  const originalTime = Date.prototype.toLocaleTimeString;

  Object.defineProperty(Date.prototype, 'toLocaleString', {
    configurable: true,
    writable: true,
    value: function toLocaleString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return Reflect.apply(originalDateTime, this, [locales, berlinOptions(locales, options)]);
    },
  });
  Object.defineProperty(Date.prototype, 'toLocaleDateString', {
    configurable: true,
    writable: true,
    value: function toLocaleDateString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return Reflect.apply(originalDate, this, [locales, berlinOptions(locales, options)]);
    },
  });
  Object.defineProperty(Date.prototype, 'toLocaleTimeString', {
    configurable: true,
    writable: true,
    value: function toLocaleTimeString(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return Reflect.apply(originalTime, this, [locales, berlinOptions(locales, options)]);
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
