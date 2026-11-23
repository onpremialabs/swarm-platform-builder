// Atajos para el código del proyecto: `t(clave)` ya ligado al espacio de
// AlejandrIA Magazine (las claves se escriben sin el prefijo `alejandria-magazine:`).
import { translate, useTranslation } from '../../../platform/i18n';
import { NAMESPACE } from './index';

export function useT() {
  return useTranslation(NAMESPACE);
}

/** `t` sin hook, para callbacks y manejadores que no deben depender del idioma. */
export function tr(key, vars) {
  return translate(key, vars, NAMESPACE);
}
