import React from 'react';

// Texto con marcas simples (<strong>, <em>, <code>) dentro de un mensaje del
// catálogo, para que una frase con énfasis sea UNA clave y no un puzle de
// fragmentos. No usa `dangerouslySetInnerHTML`: solo reconoce esas tres etiquetas
// y las pinta como elementos de React; cualquier otro texto sale como texto.
const TAGS = /<(strong|em|code)>(.*?)<\/\1>/g;

export function richParts(text) {
  const parts = [];
  let last = 0;
  for (const m of String(text).matchAll(TAGS)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push({ tag: m[1], text: m[2] });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function Rich({ text }) {
  return (
    <>
      {richParts(text).map((p, i) => (
        typeof p === 'string' ? p : React.createElement(p.tag, { key: i }, p.text)
      ))}
    </>
  );
}
