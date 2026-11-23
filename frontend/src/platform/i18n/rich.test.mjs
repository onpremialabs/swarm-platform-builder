// Pruebas del parser de marcas de `Trans`: `node --test frontend/src/platform/i18n/rich.test.mjs`
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseTags } from './rich.js';

test('texto sin marcas', () => {
  assert.deepEqual(parseTags('Hola'), ['Hola']);
});

test('una marca en mitad de la frase', () => {
  assert.deepEqual(parseTags('El <strong>Redactor</strong> la recibe'), [
    'El ', { tag: 'strong', children: ['Redactor'] }, ' la recibe',
  ]);
});

test('varias marcas y anidadas', () => {
  assert.deepEqual(parseTags('<em>a <strong>b</strong></em> c'), [
    { tag: 'em', children: ['a ', { tag: 'strong', children: ['b'] }] }, ' c',
  ]);
});

test('una marca sin cerrar se conserva como texto', () => {
  assert.equal(parseTags('a <b>sin cierre').flat().join(''), 'a <b>sin cierre');
});

test('un menor que suelto no es una marca', () => {
  assert.deepEqual(parseTags('x < y y 2 > 1'), ['x < y y 2 > 1']);
});

test('la interpolación de variables convive con las marcas', async () => {
  const core = await import('./core.js');
  core.resetI18n();
  core.registerMessages('platform', { es: { k: 'Pipeline <strong>{name}</strong> listo' } });
  assert.deepEqual(parseTags(core.translate('k', { name: 'Flujo 1' })), [
    'Pipeline ', { tag: 'strong', children: ['Flujo 1'] }, ' listo',
  ]);
});
