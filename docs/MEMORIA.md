# Memoria del proyecto

Lo que hay que saber **antes** de tocar algo. Si una sesión nueva empieza aquí, lee esto, luego
`PENDIENTES.md`, y si existe, `../private/CONTEXTO.md` (notas personales, solo en la Mac del dueño).

## Qué es

Una lista DNS para **AdGuard para iOS** que bloquea anuncios dentro de apps y telemetría sin romper
apps (bancos, chats de soporte, pagos, verificación de identidad). Se regenera sola cada día con
GitHub Actions y AdGuard la descarga de:

```
https://raw.githubusercontent.com/acidgeek/dns-blocklist/main/dist/adguard-dns.txt
```

## Cómo funciona AdGuard iOS por dentro (verificado en su código fuente)

| Hecho | Dónde se verificó | Consecuencia |
|---|---|---|
| Los anuncios **dentro de apps** solo se bloquean por DNS (Protección DNS). Los filtros de Safari no aplican a apps ni a Brave. | arquitectura iOS | Todo el esfuerzo va a filtros DNS. |
| El filtrado DNS con listas propias **requiere Premium**. | `DnsConfiguration(proStatus:)`, `ImportSettingsService` | El dueño tiene Premium. |
| Todos los filtros DNS juntos tienen un tope de **8 MiB** (`FILTER_PARAMS_MEM_LIMIT_BYTES` en DnsLibs). Cada dominio cuesta ~16 bytes. Lo que excede se **descarta en silencio** (`AGDPE_MEM_LIMIT_REACHED`, AdGuard sigue corriendo). | `DnsLibs/platform/mac/framework/AGDnsProxy.mm`, `dnsfilter/filter.cpp` | Nunca apilar listas grandes. Esta lista + el filtro integrado ≈ 6.7 MiB. |
| El motor junta las coincidencias de **todos** los filtros y una excepción `@@` gana a un bloqueo normal. | `dns_forwarder.cpp` → `get_effective_rules` | Nuestras excepciones también anulan bloqueos del filtro integrado de AdGuard. |
| Una excepción sobre el nombre consultado **también cubre su cadena CNAME** (`last_effective_rules`). | `dns_forwarder.cpp` | No hace falta exceptuar el CNAME de destino. |
| `\|host^` = coincidencia exacta; `\|\|dominio^` = dominio y subdominios. | `dnsfilter/rule_utils.cpp` | Sintaxis usada en `allow.txt`. |
| El filtro DNS integrado de AdGuard iOS es `https://filters.adtidy.org/dns/filter_1_ios.txt` (~190 k reglas). | `DefaultDnsFilterInstaller.swift` | Se usa como `reference`: no repetimos sus dominios. |
| `adguard://apply_settings?json=...` importa ajustes, **pero `dns_user_rules` REEMPLAZA todas las reglas DNS del usuario** aunque `dns_user_rules_override` sea `false` (`UserRulesManager.set` sustituye la lista). | `ImportDNSSettingsHelper.swift`, `UserRulesManager.swift` | Nunca importar `dns_user_rules`. Solo filtros (`dns_filter_list`, que sí se suma) y servidor. |
| Importación: campos `dns_filter_list` [{name,url}], `dns_filter_list_override`, `dns_server_id`, `cb_filter_*`, `user_rules`. Muestra una pantalla de confirmación con casillas. | `ImportSettings.swift` | Ver `tools/adguard_import_link.py`. |
| IDs de servidores: 3 = AdGuard DNS DoH (filtra), **30 = AdGuard DNS non-filtered DoH**. | `providers.json` | Usar **30**: si el servidor upstream filtra, bloquea antes de que nuestras excepciones puedan actuar (posible causa de roturas pasadas). |
| **Modo "Túnel dividido" se puede eludir**: solo la IP del DNS de AdGuard va por el túnel. Cuando una conexión a un dominio bloqueado falla (respuesta `0.0.0.0`), iOS la reintenta **ligada a la red celular** y la resuelve con el DNS del operador, fuera de AdGuard. Medido: 26 de 36 consultas por celular eran justo dominios bloqueados y los anuncios cargaban. La propia app lo advierte ("puede ser eludido por el sistema en caso de mala conectividad"). | `PacketTunnelSettingsProvider.swift` (split excluye la ruta por defecto), captura pcapd | **Usar "Túnel completo"** (Configuración → General → Configuración avanzada → Opciones de bajo nivel → Modo túnel). Verificado: 0 fugas. No se puede fijar por enlace de importación. |
| Con DnsLibs 2.10.1 (la que usa AdGuard iOS 4.5.x) el modo de bloqueo "Default" responde `0.0.0.0`/`::` (antes de 2.10.0 era REFUSED). | `DnsLibs/CHANGELOG.md`, `project.pbxproj` | No hace falta cambiar el modo de bloqueo. |
| AdGuard usa una VPN local con "conectar bajo demanda", pero **iOS solo permite una VPN activa**. Si otra VPN (p. ej. una VPN para entrar a la red de casa) toma el control, AdGuard queda apagado y no vuelve solo. | `VpnManager.swift`, `NetworkSettingsService.swift` | Usar Atajos para alternar VPN; ver `PENDIENTES.md`. |

## Convivir con otras VPN (iOS permite una sola)

Verificado en el iPhone el 2026-11-13:

- La acción de Atajos **"Configurar VPN → Conectar"** sí controla VPN de apps (AdGuard y la VPN del
  servidor). Cambiar de una a otra tarda 3–6 s; mientras la otra está activa **no hay filtrado**.
- Patrón usado: automatización "al abrir la app que necesita la otra VPN → conectarla" y "al cerrarla →
  conectar AdGuard"; para una página web, un atajo: conectar VPN → esperar 2 s → "Mostrar vista web" →
  conectar AdGuard (la última acción corre al cerrar la vista con la X).
- "Al cerrar la app" se dispara en cuanto la app deja la pantalla (inicio o cambio de app); no hace falta
  forzar el cierre. Riesgo: cortar reproducción en segundo plano/PiP (sin probar).
- Si el atajo se interrumpe a mitad (p. ej. se abre otra app con la vista web abierta, o la primera vez que
  pide permiso para abrir la URL), la otra VPN queda seleccionada y **AdGuard apagado**. Recuperar:
  Configuración → VPN → AdGuard. Comprobar en Configuración → VPN cuál está seleccionada y si dice "Conectado".
- No usar la "integración" de AdGuard VPN: necesita el túnel dividido de AdGuard, que es eludible.
- Para VPN de uso ocasional sin automatización segura (cortaría la VPN al cambiar de app): volver a AdGuard
  a mano al terminar.

## AdGuard para Android (verificado 2026-11-16 en una tablet con Android 16, AdGuard 4.15.2)

- La versión completa (`com.adguard.android`) se instala desde adguard.com, no desde Play, y se
  actualiza sola desde la app (Configuración → General → Actualizaciones de la app y filtros, o el botón ↻).
  Android solo instala una actualización firmada con la misma clave.
- **"DNS privado" de Android debe estar desactivado.** En modo "Automático", Android cifra el DNS hacia el
  servidor que da el router (p. ej. Google) y **se salta el filtro DNS de AdGuard**; la app lo avisa en
  Protección DNS. Por ADB: `settings put global private_dns_mode off`.
- Suscribir la lista: Protección → Protección DNS → Filtros DNS → Agregar filtro DNS → URL. Servidor:
  "AdGuard DNS Non-filtered" (DNS-over-HTTPS), por la misma razón que en iOS.
- **El filtro DNS integrado de Android es distinto al de iOS y cambia con las versiones.** Con 4.15 bloquea
  `lptag.liveperson.net` (chat de bancos), que el de iOS no bloquea. Por eso la lista publica **siempre** las
  excepciones curadas de `lists/allow.txt` (ver "Excepciones" abajo).
- En Samsung conviene exentar AdGuard del ahorro de batería y darle "alarmas y recordatorios"; si no, la
  app advierte que las actualizaciones automáticas pueden fallar (y el sistema puede cerrarla). Por ADB:
  `dumpsys deviceidle whitelist +com.adguard.android`, `appops set com.adguard.android RUN_ANY_IN_BACKGROUND allow`,
  `appops set com.adguard.android SCHEDULE_EXACT_ALARM allow`.
- AdGuard trae telemetría propia activada ("Informe automático de fallos", "Enviar datos técnicos y de
  interacción" en Configuración → General); se pueden apagar sin afectar el bloqueo.
- Diagnóstico: Estadísticas → Actividad reciente → detalle de la petición muestra **qué regla y qué filtro**
  bloquearon. Para saber si una app falla por AdGuard: pausar la protección, reabrir la app y comparar.
- Manejo por ADB: `uiautomator dump` da texto y posiciones exactas (más fiable que coordenadas a ojo);
  `input text` escribe URLs sin problema. Ojo con demasiados "atrás": se sale a otras apps.

## Excepciones: cuáles se publican

- Las de `lists/allow.txt` (curadas a mano, `"emit_always": true` en `sources.json`) se publican **siempre**,
  aunque hoy nada las bloquee: protegen contra filtros integrados de otras plataformas/versiones y listas
  que el usuario active.
- Las de fuentes remotas (whitelist comunitaria de Pi-hole, excepciones del filtro de AdGuard) solo se
  publican si algo de esta lista o del filtro de referencia las bloquea: así una lista remota comprometida no
  puede desbloquear dominios en todos los filtros. `emit_always` se ignora en fuentes remotas.

## Diseño de la lista

- **Tier 0**: `lists/block-mobile-ads.txt` (SDKs de anuncios en apps, curada a mano).
- **Tier 1** (siempre entran): HaGeZi Multi PRO, HaGeZi Apple native, AdGuard Mobile Ads filter.
- **Tier 2** (llenan el presupuesto, por votos ponderados): StevenBlack (Pi-hole por defecto, peso 2),
  Firebog "ticked" (anuncios/rastreo peso 2, malware/phishing peso 1).
- **Reference**: filtro integrado de AdGuard; sus dominios no se repiten y sus `@@` se importan.
- **Allow**: `lists/allow.txt` + whitelists comunitarias de Pi-hole (anudeepND).
- Tope: `max_rules` en `sources.json` (260 000).

### Reglas de seguridad (no romper apps)

1. Nunca bloquear un sufijo público (PSL) ni un dominio de `lists/never-block.txt`. Las listas de
   malware de Firebog traen cosas como `com.cn` o servicios de DNS dinámico completos.
2. `lists/allow.txt` por categorías: chat de soporte, antifraude/biometría, KYC, push, configuración
   remota, gestores de etiquetas, deep links, redirectores de correo y de ofertas, consentimiento,
   streaming SSAI, logins.
3. `lists/protect-hosts.txt`: si una actualización los bloquea, `build.py` crea la excepción y lo
   reporta en `dist/stats.json` → `auto_unblocked_protected_hosts`.
4. `build.py` no publica si falla una fuente principal (exit 2), si la lista baja más de 40 %
   (exit 3) o si queda un host protegido bloqueado (exit 4).

### Criterio para decidir un dominio dudoso

- Lo bloquea **HaGeZi Pro** (y/o EasyPrivacy) → confiar: está probada por muchísimos usuarios.
- Lo bloquea **solo una** lista de Pi-hole y es de una app funcional (API, seguridad, consentimiento)
  → excepción.
- Es antifraude, biometría, KYC, chat, push o 3-D Secure → excepción **siempre**.
- Es analítica pura (AppsFlyer, Adobe Analytics, Mixpanel, Amplitude, Crashlytics, Sentry, Bugsnag,
  New Relic, Dynatrace, Clarity, Segment) → bloquear.

## Herramientas para probar contra el iPhone real (`tools/iphone/`)

Requiere `pymobiledevice3` (venv de pipx), iPhone por USB, Modo de Desarrollador activo.

1. `capture.py OUT.jsonl SEGUNDOS`: graba hostnames por proceso (SNI de TLS, SNI de QUIC Initial
   descifrado, DNS, HTTP). Solo lectura.
2. `sweep.sh DIR`: abre cada app ~11 s (`core-device launch-application --native`). Lee
   `DIR/sweep_list.tsv` (bundle, ejecutable, nombre).
3. `analyze.py`: simula la lista + filtro integrado por app e imprime qué se bloquearía.
   Ojo: varias apps Flutter se llaman `Runner`; se separan por la hora en que se abrieron.

Lo ideal es grabar **sin** filtrado (AdGuard apagado) para ver todo lo que las apps intentan contactar.
Para comprobar el filtrado, grabar **con** AdGuard y buscar conexiones (SNI/QUIC) a dominios bloqueados y
consultas DNS por la interfaz celular (`pdp_ip`): ambas deben ser 0. En túnel completo las apps siguen
apareciendo con su propio nombre de proceso.

### Manejar la pantalla del iPhone desde la Mac (cuando el dueño lo pide)

- Capturas: `developer core-device screen-capture screenshot --native`. Llegan con unos segundos de
  retraso: esperar y tomar otra antes de concluir.
- Toques: `developer core-device universal-hid-service session --native` leyendo líneas `tap X Y`
  (coordenadas 0..65535). Muchos `tap` sueltos seguidos saturan el canal y dejan de funcionar; el primer
  toque tras una captura a veces se pierde.
- Texto: `type` solo escribe minúsculas/ASCII sin Mayús y con teclado español (`-`→`'`, `/` y `:` fallan).
  Para texto exacto: `developer core-device copy --native` (portapapeles del iPhone) y pegar.
- Estado de VPN sin tocar la pantalla: `developer core-device list-processes --native` y buscar
  `Tunnel.appex` (AdGuard) o la extensión de la otra VPN.
- Nunca tocar cerca de "Restablecer", "Eliminar perfil VPN" o los "−" del modo edición de iconos.
