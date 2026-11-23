import React, { useCallback, useEffect, useSyncExternalStore } from 'react';
import {
  DEFAULT_NAMESPACE, detectLocale, formatDate, formatNumber, getLocale, setLocale,
  subscribe, translate,
} from './core';

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
