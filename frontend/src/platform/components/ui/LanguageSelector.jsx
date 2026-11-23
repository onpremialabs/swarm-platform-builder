import React, { useState } from 'react';
import { SUPPORTED_LOCALES, useTranslation } from '../../i18n';

// Selector de idioma (SPEC-041 / T29.10 / AC6, AC12). Grupo de botones con
// `aria-pressed`: se opera con Tab/Enter/Espacio, el nombre accesible está en el
// idioma activo y el cambio se anuncia en una región `role="status"`. El nombre de
// cada idioma lleva su propio `lang` para que el lector lo pronuncie bien.
const OPTION_KEYS = { es: 'language.es', en: 'language.en' };

export default function LanguageSelector() {
  const { t, locale, setLocale } = useTranslation();
  const [changed, setChanged] = useState(false);

  const choose = (next) => {
    if (next === locale) return;
    setLocale(next);
    setChanged(true);
  };

  // Se compone al renderizar, ya con el catálogo del idioma elegido.
  const announcement = changed
    ? t('language.changed', { language: t(OPTION_KEYS[locale]) })
    : '';

  return (
    <div className="lang-switch" role="group" aria-label={t('language.label')}>
      {SUPPORTED_LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          className="lang-switch-btn"
          aria-pressed={code === locale}
          onClick={() => choose(code)}
        >
          {t(OPTION_KEYS[code])}
        </button>
      ))}
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
    </div>
  );
}
