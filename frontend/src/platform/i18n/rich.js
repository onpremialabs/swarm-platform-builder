// Texto con marcas simples (`<strong>`, `<em>`, ...) para el componente `Trans`
// (SPEC-041 / T29.7). Sin React y sin dependencias, para poder probarlo con
// `node --test`.
//
// Por qué existe: hay frases con una palabra en negrita en mitad ("El
// <strong>Investigador</strong> la usa para..."). Partirlas en tres claves obliga
// a quien traduce a respetar un orden de palabras que su idioma puede no admitir;
// con la marca dentro del mensaje se traduce la frase entera.
//
// Solo se admiten marcas simples y sin atributos, `<nombre>texto</nombre>`, y
// pueden anidarse. Lo que no encaje (una marca sin cerrar, un `<` suelto) se
// devuelve como texto, nunca se pierde.

const MARCA = /<([A-Za-z][\w-]*)>/;

/**
 * Parte `texto` en nodos: `string` o `{ tag, children }` (children es otra lista).
 */
export function parseTags(texto) {
  const salida = [];
  let resto = String(texto);
  while (resto.length > 0) {
    const m = MARCA.exec(resto);
    if (!m) {
      salida.push(resto);
      break;
    }
    const cierre = `</${m[1]}>`;
    const fin = resto.indexOf(cierre, m.index + m[0].length);
    if (fin === -1) {
      // marca sin cerrar: la apertura es texto y se sigue después de ella
      salida.push(resto.slice(0, m.index + m[0].length));
      resto = resto.slice(m.index + m[0].length);
      continue;
    }
    if (m.index > 0) salida.push(resto.slice(0, m.index));
    salida.push({ tag: m[1], children: parseTags(resto.slice(m.index + m[0].length, fin)) });
    resto = resto.slice(fin + cierre.length);
  }
  return salida;
}
