// Aviso persistente de lo que se está ejecutando (SPEC-030 / T18.7).
//
// Vive en el shell del dashboard, por encima del `<Outlet/>`, así que cambiar de
// pestaña **no lo desmonta**. Ese es el punto: antes, lo que estaba corriendo solo
// se veía desde la pantalla de ejecución, y salir de ella equivalía a perderlo de
// vista aunque el pipeline siguiera trabajando.
//
// Se sondea en vez de abrir un SSE: es una barra de estado, no un log. Un sondeo
// ligero cada pocos segundos cuesta menos que mantener una conexión viva por
// pestaña, y si falla una vuelta no pasa nada — la siguiente lo arregla.
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Loader, ArrowRight } from 'lucide-react';
import { dashboardApi } from '../api/dashboard';
import { agentMeta } from '../agentCatalog';

const INTERVALO_MS = 5000;

export default function RunningBar() {
  const [enCurso, setEnCurso] = useState([]);
  const location = useLocation();

  const consultar = useCallback(async () => {
    try {
      const datos = await dashboardApi.getRunning();
      setEnCurso(datos?.running || []);
    // mejor-esfuerzo: es un aviso, no el dato. Si una vuelta falla se conserva
    // lo último que se supo y la siguiente lo corrige; vaciar la barra por un
    // fallo de red diría «ya no corre nada», que sería falso.
    } catch { }
  }, []);

  useEffect(() => {
    consultar();
    const id = setInterval(consultar, INTERVALO_MS);
    return () => clearInterval(id);
  }, [consultar]);

  if (enCurso.length === 0) return null;

  // Si ya estás mirando esa ejecución, la barra sobra: ofrecer «volver» a donde
  // ya estás es ruido.
  const visibles = enCurso.filter(
    r => !location.pathname.endsWith(`/execution/${r.article_id}`)
  );
  if (visibles.length === 0) return null;

  return (
    <div className="running-bar" role="status" aria-live="polite">
      {visibles.map(run => {
        const meta = agentMeta(run.current_agent) || {};
        return (
          <div key={run.article_id} className="running-bar-item">
            <Loader size={14} className="running-bar-spin" />
            <span className="running-bar-text">
              <strong>{run.title}</strong>
              {run.current_agent
                ? <> — {meta.label || run.current_agent}
                    {run.flow_sequence?.length > 0 && (
                      <> ({run.flow_sequence.indexOf(run.current_agent) + 1} de {run.flow_sequence.length})</>
                    )}
                  </>
                : <> — preparando…</>}
            </span>
            <Link to={`/dashboard/execution/${run.article_id}`} className="running-bar-link">
              Ver ejecución <ArrowRight size={13} />
            </Link>
          </div>
        );
      })}
    </div>
  );
}
