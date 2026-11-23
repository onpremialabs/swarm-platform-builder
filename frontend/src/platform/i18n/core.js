// Núcleo de i18n del builder (SPEC-041 / T29.6 / AC6, AC8). Sin React y sin
// dependencias: una implementación ligera sobre `Intl` (plurales, números,
// fechas) en lugar de i18next, que aquí aportaría más peso que valor.
//
// Capas: el builder expone `registerMessages(namespace, catalogs)` y el proyecto
// lo invoca al arrancar desde main.jsx, igual que `setAgentCatalog`. Este módulo
// no importa nada de `projects/`.
//
// Claves: `espacio:ruta.de.clave` (p. ej. `platform:nav.home`). Sin espacio se usa
// `platform`. Los catálogos pueden ser anidados; se aplanan con puntos. Plurales:
// `clave_one`, `clave_other`, ... según `Intl.PluralRules` y la variable `count`.
// Interpolación: `{nombre}`.

export const SOURCE_LOCALE = 'es';
export const SUPPORTED_LOCALES = ['es', 'en'];
export const DEFAULT_NAMESPACE = 'platform';
export const STORAGE_KEY = 'ui.locale';

const catalogs = new Map(); // espacio -> { locale -> { clave plana -> texto } }
const listeners = new Set();
let locale = SOURCE_LOCALE;

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object') flatten(v, key, out);
    else out[key] = String(v);
  }
  return out;
}

function emit() {
  listeners.forEach((fn) => fn());
}

/** Alta (o ampliación) de los mensajes de un espacio: `{ es: {...}, en: {...} }`. */
export function registerMessages(namespace, byLocale) {
  if (!namespace) throw new Error('registerMessages: falta el espacio de nombres');
  const actual = catalogs.get(namespace) || {};
  for (const [loc, msgs] of Object.entries(byLocale || {})) {
    actual[loc] = { ...(actual[loc] || {}), ...flatten(msgs) };
  }
  catalogs.set(namespace, actual);
  emit();
}

export function registeredNamespaces() {
  return [...catalogs.keys()];
}

/** Idioma soportado más cercano a `candidate` (`en-US` -> `en`) o null. */
export function normalizeLocale(candidate) {
  if (!candidate) return null;
  const base = String(candidate).toLowerCase().split(/[-_]/)[0];
  return SUPPORTED_LOCALES.includes(base) ? base : null;
}

function readStored() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
  } catch {
    // mejor-esfuerzo: sin almacenamiento se detecta por el navegador
    return null;
  }
}

/** Guardado -> idioma del navegador -> español. */
export function detectLocale({ stored, navigatorLanguages } = {}) {
  const guardado = stored !== undefined ? stored : readStored();
  const langs = navigatorLanguages
    || (typeof navigator !== 'undefined' ? navigator.languages || [navigator.language] : []);
  return normalizeLocale(guardado)
    || langs.map(normalizeLocale).find(Boolean)
    || SOURCE_LOCALE;
}

export function getLocale() {
  return locale;
}

/** Cambia el idioma sin recargar; devuelve el aplicado (null si no se soporta). */
export function setLocale(next, { persist = true } = {}) {
  const loc = normalizeLocale(next);
  if (!loc) return null;
  if (loc !== locale) {
    locale = loc;
    if (typeof document !== 'undefined') document.documentElement.lang = loc;
    emit();
  }
  if (persist) {
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, loc);
    } catch {
      // mejor-esfuerzo: sin almacenamiento la preferencia vale solo por sesión
      return loc;
    }
  }
  return loc;
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function interpolate(text, vars) {
  return text.replace(/\{(\w+)\}/g, (m, name) => (
    vars && vars[name] !== undefined && vars[name] !== null ? String(vars[name]) : m
  ));
}

function lookup(ns, loc, key, vars) {
  const cat = catalogs.get(ns)?.[loc];
  if (!cat) return undefined;
  if (vars && typeof vars.count === 'number') {
    const form = new Intl.PluralRules(loc).select(vars.count);
    if (cat[`${key}_${form}`] !== undefined) return cat[`${key}_${form}`];
    if (cat[`${key}_other`] !== undefined) return cat[`${key}_other`];
  }
  return cat[key];
}

/**
 * Traduce `clave`. Orden: idioma activo -> español (fuente) -> la propia clave
 * (visible y fácil de detectar, nunca una cadena vacía).
 */
export function translate(key, vars, defaultNamespace = DEFAULT_NAMESPACE) {
  const i = key.indexOf(':');
  const ns = i > 0 ? key.slice(0, i) : defaultNamespace;
  const bare = i > 0 ? key.slice(i + 1) : key;
  const text = lookup(ns, locale, bare, vars) ?? lookup(ns, SOURCE_LOCALE, bare, vars);
  return text === undefined ? key : interpolate(text, vars);
}

export const formatNumber = (n, opts) => new Intl.NumberFormat(locale, opts).format(n);
export const formatDate = (d, opts) => new Intl.DateTimeFormat(locale, opts).format(new Date(d));

/** Solo para tests: vacía el registro y vuelve al idioma fuente. */
export function resetI18n() {
  catalogs.clear();
  locale = SOURCE_LOCALE;
  emit();
}
