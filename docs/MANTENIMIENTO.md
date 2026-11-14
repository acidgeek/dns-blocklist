# Mantenimiento: cómo se mantiene solo y cómo escala

La idea es que **no tengas que acordarte de nada**: la lista se actualiza sola, se protege sola y te
avisa cuando necesita una persona.

## 1. Automático, todos los días (ya está)

GitHub Actions (`.github/workflows/build.yml`) a las 03:17 (hora de México):

1. Corre las pruebas.
2. Descarga todas las fuentes de Pi-hole, HaGeZi y AdGuard (siempre las versiones más nuevas; si
   Firebog agrega o quita listas, se adapta sola porque lee su índice).
3. Compila con las reglas de seguridad y **no publica** si algo se ve mal.
4. Si cambió, publica `dist/adguard-dns.txt`. AdGuard la descarga solo.
5. **Si algo requiere atención, abre un Issue** en el repositorio (GitHub te manda correo):
   - la compilación falló o se negó a publicar;
   - una lista nueva empezó a bloquear un host protegido (se exceptuó solo, pero conviene revisarlo);
   - un dominio de anuncios conocido dejó de estar bloqueado.

## 2. Cuando algo se rompe o se cuela un anuncio (tú, 1 minuto)

Desde el celular, en GitHub → Issues → New issue, elige:

- **"Una app dejó de funcionar"**: app, qué falla, hora aproximada.
- **"Se cuela un anuncio"**: app y dónde aparece.

Con eso, en una sesión de mantenimiento: se revisa AdGuard → Actividad o se graba la app con
`tools/iphone/verify.sh`, se agrega la excepción o el bloqueo, y el push regenera la lista.

## 3. Verificación contra el iPhone (mensual o al instalar apps nuevas)

Un solo comando, con el iPhone conectado por USB y desbloqueado:

```sh
tools/iphone/verify.sh            # abre todas tus apps, graba, simula la lista y genera un reporte
```

Detecta solo las apps instaladas, así que **escala**: si instalas 20 apps nuevas, entran en la
siguiente verificación sin tocar nada. El reporte queda en `private/` (no se publica) y marca
cualquier bloqueo en apps de banca, salud, pagos o gobierno para revisarlo.

## 4. Opcional: revisión semanal automatizada

Se puede programar una tarea semanal que lea `dist/stats.json`, compare con la semana
anterior, revise si alguna fuente cambió mucho y abra un PR con ajustes propuestos. Solo se activa si
la pides.

## Qué NO escala y por qué

- **Anuncios propios** de redes sociales y streaming: no se pueden quitar por DNS sin romper la app.
- **El tope de 8 MiB** es de AdGuard en iOS. Más listas no equivalen a más bloqueo: pasado el tope,
  se pierden reglas. Por eso la lista elige por consenso entre fuentes.
- **iOS permite una sola VPN.** Mientras otra VPN esté activa, AdGuard no filtra. La solución es con
  Atajos (ver `PENDIENTES.md`) o, a futuro, poner el mismo filtrado en el DNS de esa VPN (p. ej. una tailnet) apuntando a
  un AdGuard Home o Pi-hole en tu servidor (así filtra aunque esa VPN esté encendida).
