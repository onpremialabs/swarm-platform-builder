import React, { useCallback, useEffect, useSyncExternalStore } from 'react';
import {
  DEFAULT_NAMESPACE, detectLocale, formatDate, formatNumber, getLocale, setLocale,
  subscribe, translate,
} from './core';
import { parseTags } from './rich';

export {
  registerMessages, getLocale, setLocale, translate, SUPPORTED_LOCALES, SOURCE_LOCALE,
} from './core';

/** Hook: `t(clave, vars)` ligado a un espacio; se repinta al cambiar el idioma. */
export function useTranslation(namespace = DEFAULT_NAMESPACE) {
  const locale = useSyncExternalStore(subscribe, getLocale);
  const t = useCallback((key, vars) => translate(key, vars, namespace), [namespace, locale]);
  return { t, locale, setLocale, formatNumber, formatDate };
}

/** Fija el idioma inicial y `<html lang>` al montar la aplicación. */
export function I18nProvider({ children }) {
  useEffect(() => {
    setLocale(detectLocale(), { persist: false });
  }, []);
  return <>{children}</>;
}

/**
 * Mensaje con marcas simples: `<Trans i18nKey="x" values={{ name }} components={{ strong: <b /> }} />`.
 * Sin `components`, `<strong>` y `<em>` se pintan como los elementos HTML del mismo nombre.
 */
export function Trans({ i18nKey, values, components = {}, namespace }) {
  const { t } = useTranslation(namespace);
  const render = (nodos) => nodos.map((n, i) => {
    if (typeof n === 'string') return <React.Fragment key={i}>{n}</React.Fragment>;
    const hijos = render(n.children);
    const base = components[n.tag] || React.createElement(n.tag);
    return React.cloneElement(base, { key: i }, hijos);
  });
  return <>{render(parseTags(t(i18nKey, values)))}</>;
}
