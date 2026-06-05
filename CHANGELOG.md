# LAFA / Nexiu — Dashboard de Reclutamiento
## Historial de lo construido

---

## Arquitectura final

```
Railway app  (lafa-nexiu-os-production.up.railway.app)
    │
    │  sync_railway.py   ← Playwright, Google OAuth, descarga .xlsx
    ▼
/Users/ivan/Code/vibe-coding/nexiu/LAFA/
    hr_os_funnel_Rango_…_Nexiu_YYYY-MM-DD.xlsx
    │
    │  upload_to_supabase.py   ← upsert, nulls stripped, synced_at stamp
    ▼
Supabase  ·  tabla: funnel
    │
    │  fetch() al cargar la página
    ▼
LAFA/recruitment-dashboard.html   (vanilla JS + Chart.js)
```

**Trigger:** launchd dispara a las **9:00 · 9:15 · 9:30 am** (hora México).
La primera corrida exitosa escribe `.last_sync_date`; las demás salen inmediatamente.

---

## Sync agent (`sync_railway.py`)

| Flag | Efecto |
|---|---|
| *(ninguno)* | Headless, salta si ya corrió hoy |
| `--force` | Corre aunque ya haya corrido hoy |
| `--headed` | Browser visible |
| `--no-upload` | Solo descarga, no sube a Supabase |
| `--explore` | Imprime snapshot de UI, no sube |

**Sesión persistente:** `browser_session/` guarda cookies de Google OAuth → el login solo ocurre la primera vez (o si expira). Si falla, re-inicializar con:
```bash
rm -rf browser_session/
python3 sync_railway.py --headed --force
```

**Flujo interno:**
1. Navega a Railway workflow
2. Si hay login screen → clic "Iniciar sesión con Google" → llena email/password
3. Clic "Descargar funnel" → modal → selecciona "Rango de días"
4. Llena `#crm-funnel-report-start` = 2026-04-01 · `#crm-funnel-report-end` = hoy
5. Clic "Descargar: Rango …" → guarda xlsx en `LAFA/`
6. Llama a `upload_to_supabase.py` con el archivo y `--periodo 2026-04-01_YYYY-MM-DD`

---

## launchd (`~/Library/LaunchAgents/com.nexiu.lafa.sync.plist`)

```bash
# Verificar estado
launchctl list | grep nexiu

# Recargar tras editar el plist
launchctl unload ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist
launchctl load   ~/Library/LaunchAgents/com.nexiu.lafa.sync.plist

# Disparar ahora
launchctl start com.nexiu.lafa.sync

# Ver log en tiempo real
tail -f /Users/ivan/Code/vibe-coding/nexiu/LAFA/sync_railway.log
```

---

## `upload_to_supabase.py`

**Fixes críticos aplicados:**
- **Null-strip:** campos vacíos no se envían → no sobreescriben datos válidos en Supabase
- **PGRST102:** agrupa registros por frozenset de keys antes de batchear (todos los objetos de un batch deben tener las mismas keys)
- **PGRST204:** columna desconocida → se añade a `skip_fields` y se reintenta sin ella
- **`synced_at`:** timestamp UTC inyectado en cada registro para saber la hora exacta del último sync

**Uso manual:**
```bash
python3 upload_to_supabase.py archivo.xlsx
python3 upload_to_supabase.py archivo.xlsx --periodo 2026-05-01_2026-05-31
```

---

## Supabase — tabla `funnel`

| Columna | Tipo | Descripción |
|---|---|---|
| `id_candidato` | text PK | Llave de upsert |
| `candidato` | text | Nombre |
| `canal` | text | Facebook, DiDi, etc. |
| `inicio` | date | Fecha de agenda (YYYY-MM-DD) |
| `hora_llegada` | date | Fecha de llegada real |
| `asistencia` | text | `'Realizada'` = asistió |
| `estado_entrevista` | text | Aprobado / No aprobado / Se retiró… |
| `suma_bg` | text | `'Aprobado'` = pasó entrevista + BG |
| `prueba_manejo` | text | `'Aprobado'` / `'No aprobado'` |
| `firma_contrato` | date | Fecha de contratación |
| `status_driver` | text | Estado final |
| `declina_oferta` | text | `'Sí'` si rechazó |
| `onboarding_dia` | text | Día asignado |
| `asistencia_onboarding` | text | Si asistió al onboarding |
| `docs_y_didi` | text | Documentos y DiDi |
| `razon_declina` | text | Razón de declive |
| `razon_no_aprobado` | text | Razón prueba de manejo |
| `entrevistador` | text | Nombre del entrevistador |
| `background_check` | text | Resultado BG |
| `ultima_modificacion` | text | Última mod en Railway |
| `periodo` | text | `'2026-04-01_2026-06-05'` |
| `synced_at` | timestamptz | Hora exacta del sync |

---

## Dashboard (`LAFA/recruitment-dashboard.html`)

Archivo único, sin build, sin framework. Datos desde Supabase REST API al cargar.

### Header
- **"Actualizado: 5 jun. 2026, 9:28 a.m."** → lee `max(synced_at)` de los rows, formatea en hora México.

### Tabs

#### Executive
- **8 KPI cards:** Total candidatos · Tasa presentación · Aprobación entrevista · Prueba manejo · Contratados · Conversión total · Declinaron oferta · Pipeline activo
- **Gráficas semanales (1–7):**
  1. Funnel de Reclutamiento (barras horizontales con %)
  2. Tasas de conversión por semana (líneas)
  3. Candidatos captados por semana
  4. Asistentes por semana
  5. Entrevistas aprobadas por semana
  6. Pruebas de manejo aprobadas por semana
  7. Contrataciones por semana
- **Gráficas mensuales (2M–7M):**
  - Mismas métricas pero agrupadas por mes
  - Mes actual: barra real (sólido) + segmento proyectado al fin de mes (transparente)
  - **Valor** centrado dentro de cada segmento de barra
  - **Crecimiento MoM (▲/▼X%)** encima de la barra completa
  - Proyección proporcional: `actual × (días_en_mes / día_actual)`

#### Detalle Asistencia
- Asistencia acumulada WTD vs semanas previas
- Asistencia diaria por semana
- Comparativa mismo día · últimas semanas
- Asistencia efectiva de reagendados
- Backup detalle de presentes por semana

#### Pipeline Activo
- Evolución del pipeline activo (corte viernes 3pm hora México)
- Tabla pivot: etapas × semanas
- Lista detallada de candidatos activos con export CSV
- **6 etapas:** Pendiente entrevista → Entrevista aprobada → BackCheck → PM aprobada → Onboarding → Post-onboarding

#### Backup
- Gráficas 8–14 (render lazy al primer clic):
  8. Resultado de entrevistas (donut)
  9. Detalle de no aprobados en entrevista
  10. Resultado de prueba de manejo (donut)
  11. Detalle de no aprobados en prueba de manejo
  12. Status Driver (barras horizontales)
  13. Candidatos sin Status Driver
  14. Razones para declinar oferta
- Conclusiones del mes (insights estáticos)

### Funciones JS clave
| Función | Qué hace |
|---|---|
| `fetchAll()` | Paginación automática hasta traer todos los rows |
| `renderFunnel(rows)` | Funnel HTML con barras y % |
| `updateKPIs(rows)` | 8 tarjetas de KPI |
| `renderCharts(rows)` | Gráficas semanales + llama a `renderMonthlyCharts` |
| `renderMonthlyCharts(rows)` | Gráficas mensuales con proyección y MoM% |
| `renderDetalleAsistencia(rows)` | Tab de detalle |
| `renderPipeline(rows)` | Tab pipeline activo |
| `renderBackup(rows)` | Tab backup (lazy, solo primera vez) |
| `makeChart(id, config)` | Destruye instancia previa antes de crear |
| `isActivePipeline(r)` | Filtra candidatos en pipeline activo |
| `getPipelineStage(r)` | Mapea candidato a una de 6 etapas |
| `isoWeek(dateStr)` | Semana ISO sin desfase UTC |

---

## Bugs corregidos en sesión

| Bug | Síntoma | Fix |
|---|---|---|
| Nulls sobreescribían datos | `firma_contrato` válidos borrados por sync | Strip de Nones antes de upsert |
| PGRST102 | Error al subir batches | Agrupar por frozenset de keys |
| `networkidle` timeout | Sync headless fallaba | Cambió a `wait_for_load_state('load')` |
| `ctx.dataset.index` | Datalabels no se mostraban | Corregido a `ctx.datasetIndex` |
| Denominador proyectado en tasas | Tasa conversión de junio ~6× deflada | Siempre usar total real como denominador |
| Código `contratacionesChart` huérfano | Todo el JS dejaba de ejecutar | Movido de vuelta dentro de `renderCharts()` |
| `datalabels.labels` por dataset | Labels no aparecían | Movido a `options.plugins.datalabels.labels` |

---

## GitHub Actions (desactivado)

`.github/workflows/sync-funnel.yml` — solo `workflow_dispatch` (manual).
Los datos vienen exclusivamente de Railway vía `sync_railway.py`.

---

*Última actualización: 2026-06-05*
