// Pruebas del núcleo i18n: `node --test frontend/src/platform/i18n/i18n.test.mjs`
import test from 'node:test';
import assert from 'node:assert/strict';
import * as i18n from './core.js';

test.beforeEach(() => i18n.resetI18n());

test('espacios de nombres, anidado y fallback al español', () => {
  i18n.registerMessages('platform', { es: { nav: { home: 'Inicio' }, solo: 'Solo es' }, en: { nav: { home: 'Home' } } });
  i18n.registerMessages('proyecto', { es: { titulo: 'Artículos' } });
  assert.equal(i18n.translate('nav.home'), 'Inicio');
  assert.equal(i18n.translate('proyecto:titulo'), 'Artículos');
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.translate('nav.home'), 'Home');
  assert.equal(i18n.translate('solo'), 'Solo es');
  assert.equal(i18n.translate('no.existe'), 'no.existe');
});

test('interpolación y plurales con Intl.PluralRules', () => {
  i18n.registerMessages('platform', {
    es: { saludo: 'Hola {name}', n_one: '{count} fuente', n_other: '{count} fuentes' },
    en: { n_one: '{count} source', n_other: '{count} sources' },
  });
  assert.equal(i18n.translate('saludo', { name: 'Ana' }), 'Hola Ana');
  assert.equal(i18n.translate('saludo'), 'Hola {name}');
  assert.equal(i18n.translate('n', { count: 1 }), '1 fuente');
  assert.equal(i18n.translate('n', { count: 3 }), '3 fuentes');
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.translate('n', { count: 1 }), '1 source');
});

test('detección de idioma y rechazo de idiomas no soportados', () => {
  assert.equal(i18n.detectLocale({ stored: 'en', navigatorLanguages: ['es'] }), 'en');
  assert.equal(i18n.detectLocale({ stored: null, navigatorLanguages: ['fr-FR', 'en-US'] }), 'en');
  assert.equal(i18n.detectLocale({ stored: null, navigatorLanguages: ['fr'] }), 'es');
  assert.equal(i18n.setLocale('fr', { persist: false }), null);
  assert.equal(i18n.getLocale(), 'es');
});

test('cambiar de idioma notifica a los suscriptores', () => {
  let n = 0;
  const off = i18n.subscribe(() => { n += 1; });
  i18n.setLocale('en', { persist: false });
  assert.equal(n, 1);
  off();
  i18n.setLocale('es', { persist: false });
  assert.equal(n, 1);
});

test('formatos según el idioma activo', () => {
  i18n.setLocale('en', { persist: false });
  assert.equal(i18n.formatNumber(1234.5), '1,234.5');
});
