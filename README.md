# Blockchain de incidentes de seguridad informática

Proyecto académico en Python con Tkinter, sockets TCP/IP, mensajes JSON,
Proof of Work, Fernet, persistencia y sincronización entre nodos. Se amplía el
proyecto existente: se conservan las clases `Bloque`, `Blockchain`, `Incidente`
y `Encriptador`, las operaciones de la GUI y la consola.

## Arquitectura y responsabilidades

```text
GUI / consola (cliente TCP)
          |
          v
  Nodo A <---- TCP + JSON ----> Nodo B <----> Nodo C
     |                            |            |
 Blockchain propia          Blockchain     Blockchain
 en memoria + JSON          propia + JSON  propia + JSON
```

- `core/incidente.py`: transacciones; cifra descripción y autor al crearlas.
  Reconstruye incidentes cifrados sin alterar timestamps ni volver a cifrarlos.
- `core/bloque.py`: bloque propuesto, múltiples transacciones, SHA-256, nonce,
  PoW, serialización y comprobación de bloques recibidos.
- `core/blockchain.py`: Génesis, encadenamiento y validación completa de cadenas.
- `servidor/servidor.py`: único código de servidor; cada proceso mantiene una
  cadena independiente, su bloque propuesto y contador de incidentes.
- `servidor/persistencia.py`: lectura validada y reemplazo atómico del JSON.
- `servidor/consenso.py`: comparación explícita por trabajo acumulado.
- `servidor/nodos.py`: vecinos configurados, propagación y sincronización.
- `comunicacion.py`: mensajes JSON UTF-8 delimitados por un salto de línea.
- `cliente/cliente.py`: solicitudes TCP, sin importar ni modificar objetos core.
- `interfaz/gui_incidentes.py`: presentación y minado solicitado en segundo plano.
- `main.py`, `gui_incidentes.py`, `blockchain_incidentes.py`: entradas compatibles.
- `tests/`: pruebas originales y nuevas; claves y archivos de prueba temporales.

## Preparación

Requiere Python 3.10 o posterior con Tkinter:

```powershell
python -m pip install -r requirements.txt
```

Si `python` no está en PATH, usa la ruta del intérprete. En esta máquina las
pruebas se ejecutaron con:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m unittest discover -s tests -v
```

En los comandos siguientes puedes sustituir `python` por
`& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"` en PowerShell.
Ejecuta los comandos desde la raíz del repositorio.

## Ejecutar tres nodos

Inicia el primer nodo y espera su mensaje de arranque antes de abrir los otros.
Se reutiliza `clave_secreta.key` de la raíz. Si es la primera ejecución del
proyecto, el primer nodo la crea. Los demás nodos necesitan esa misma clave para
autenticar y descifrar los incidentes compartidos.

Terminal 1:

```powershell
python -m servidor.servidor --puerto 7000 --nodo 127.0.0.1:7001 --nodo 127.0.0.1:7002
```

Terminal 2:

```powershell
python -m servidor.servidor --puerto 7001 --nodo 127.0.0.1:7000 --nodo 127.0.0.1:7002
```

Terminal 3:

```powershell
python -m servidor.servidor --puerto 7002 --nodo 127.0.0.1:7000 --nodo 127.0.0.1:7001
```

Los puertos de la CLI se validan entre **7000 y 8000**. No hay una cantidad fija
de nodos: repite `--nodo HOST:PUERTO` para configurar los vecinos de cada proceso.
No hay descubrimiento automático: para cambiar esa lista reinicia el proceso
con sus nuevos argumentos. La comunicación puede recorrer vecinos intermedios;
una malla completa como la del ejemplo facilita la demostración.

También funciona `python main.py servidor --puerto 7000 --nodo 127.0.0.1:7001`.
Las opciones adicionales son:

- `--host`: interfaz IPv4 local donde escuchar; predeterminada `127.0.0.1`.
- `--dificultad`: dificultad inicial de una cadena nueva, entre 0 y 8; por defecto 4.
- `--datos`: directorio del JSON de ese nodo; por defecto la raíz del repositorio.
- `--clave`: archivo Fernet; por defecto `clave_secreta.key` de la raíz.

Cada proceso debe usar su propio puerto y archivo. Por defecto se generan:

```text
<raíz>/blockchain_7000.json
<raíz>/blockchain_7001.json
<raíz>/blockchain_7002.json
```

Aunque estén en la misma carpeta, son tres archivos diferentes. Ningún nodo lee
el archivo de otro nodo. `--datos` permite incluso ponerlos en carpetas separadas.
Las pruebas con tres procesos comprueban esa independencia.

## Abrir la GUI o la consola

Terminal 4:

```powershell
python main.py gui --host 127.0.0.1 --puerto 7000
```

Entradas alternativas:

```powershell
python gui_incidentes.py --host 127.0.0.1 --puerto 7001
python main.py consola --puerto 7000
python blockchain_incidentes.py --puerto 7000
```

`python main.py` abre la GUI en `127.0.0.1:7000`. El botón **Servidor** permite
cambiar la conexión, por ejemplo a `127.0.0.1:7002`. Se conservan agregar incidentes,
ver la cadena y sus detalles, ver el bloque propuesto, minar, cambiar dificultad
y refrescar. La GUI solo utiliza datos JSON; el descifrado se solicita al nodo.

## Persistencia y arranque

El archivo contiene `version`, `dificultad` local para el próximo minado y `cadena`.
Cada bloque conserva `numero_bloque`, `hash_anterior`, `timestamp`, `nonce`, `hash`,
`dificultad` histórica y `transacciones`. Los incidentes contienen ID, tipo,
severidad, timestamp y los dos tokens Fernet cifrados. No se guardan copias de
descripción ni autor en texto plano.

Si el archivo existe, se reconstruye con `from_dict`, se valida toda la cadena
y se autentican los tokens Fernet. Este camino **no llama al constructor que
crea el Génesis** y no ejecuta minado. Si el JSON está corrupto, la cadena es
inválida o falta su clave original, el arranque falla con un mensaje; no se
sobrescribe el archivo con otra cadena.

Si el archivo no existe, se crea y mina el Génesis y se guarda inmediatamente.
Después de minar, aceptar un bloque remoto o adoptar otra cadena válida, el nodo
escribe un temporal en el mismo directorio, hace `flush` y `fsync`, y usa
`os.replace`. Solo entonces cambia el estado confirmado en memoria. Un error de
escritura conserva la cadena anterior y permite reintentar el bloque propuesto.
El cambio de dificultad local también se persiste.

Los incidentes todavía propuestos no se persisten: se pierden al cerrar el nodo.
Los datos generados y la clave están excluidos de Git.

## Génesis compartido

La estrategia de esta versión es un Génesis determinista: número 0, hash anterior
`"0"`, sin transacciones y timestamp fijo **0**. Conserva el minado con SHA-256,
nonce y ceros iniciales; no se fija un hash arbitrario. Con la misma dificultad
inicial todos calculan exactamente el mismo Génesis.

Todos los nodos nuevos de una red deben usar la **misma dificultad inicial**
(por defecto 4). Para una red de pruebas rápida, usa `--dificultad 1` en todos
desde su primera ejecución. No mezcles archivos de redes con diferente Génesis.
Al sincronizar se exige el mismo hash de Génesis; una red incompatible se rechaza.

Una cadena ya guardada conserva exactamente su Génesis, timestamps, nonces y
hashes. En un reinicio `--dificultad` no sustituye la configuración persistida;
para cambiar el próximo minado usa la GUI o `CAMBIAR_DIFICULTAD`.
La versión anterior no tenía persistencia: no es posible recuperar bloques que
solo existían en la RAM de un proceso ya cerrado. No se migran JSON externos
sin dificultad histórica ni se alteran hashes existentes para adaptarlos.

## Validación y Proof of Work

`Blockchain.validar_cadena()` devuelve `True` si todo es correcto y lanza
`ValueError` con una explicación si encuentra un problema. Comprueba:

1. Cadena no vacía y Génesis coherente.
2. Secuencia de números desde 0 y enlaces `hash_anterior`.
3. Estructura, tipos y timestamps finitos de bloques y transacciones.
4. SHA-256 recalculado igual al hash recibido, sin cambiar ningún campo.
5. PoW según la dificultad histórica de cada bloque.
6. Transacciones cifradas con estructura Fernet e IDs sin duplicados.
7. Ausencia de bloques vacíos fuera del Génesis y hashes duplicados.

El servidor autentica además los tokens con su clave Fernet antes de confirmar
datos externos. Los métodos siguen rechazando nuevas transacciones o reminado
en bloques cerrados. Un bloque recibido se reconstruye y valida; **no se vuelve
a minar**. Estos objetos mantienen la API del proyecto; no son objetos Python
congelados. El cliente no tiene acceso a ellos.

## Consenso y dificultad variable

La dificultad histórica está incluida en el contenido protegido por SHA-256.
Cambiar la dificultad para un bloque nuevo no invalida los anteriores.
La regla está separada en `servidor/consenso.py`:

```text
trabajo de un bloque = 16 ** dificultad
trabajo de la cadena = suma del trabajo de sus bloques
preferir la cadena válida con mayor trabajo acumulado
```

Con dificultad constante equivale a preferir la cadena válida más larga.
Con dificultad variable una cadena más larga puede tener menos trabajo y se
rechaza si su puntaje es inferior. Se estima trabajo por el objetivo de PoW;
el nonce no cuenta intentos medibles de otros mineros.

En empate de trabajo se elige el hash final numéricamente menor para que las
ramas puedan converger de forma determinista. La cadena candidata se valida
completamente y se compara con la cadena local actual bajo candado antes de
reemplazarla. Se mantienen la dificultad local para el próximo minado y los
campos originales de todos los bloques recibidos.

Si una reorganización descarta una rama local, sus incidentes se devuelven al
bloque propuesto junto con los que ya estaban pendientes. Solo esas transacciones
no confirmadas pueden recibir nuevos IDs para evitar colisiones con la cadena
adoptada; no se modifica ninguna transacción confirmada.

## Propagación y sincronización

Después de confirmar y guardar un bloque, se encola su propagación a los vecinos.
Cada receptor valida hash, PoW, número, padre y transacciones antes de guardarlo.
Los hashes ya presentes se responden como `duplicado` y no se vuelven a propagar.
Se omite también el vecino indicado como origen cuando coincide con la lista
conocida. Esto evita rebotes infinitos incluso en una red con ciclos.

Un hilo por nodo consulta las cadenas de sus vecinos al arrancar y aproximadamente
cada **5 segundos**, además de atender la cola de propagación. Si recibe un bloque
que no enlaza con su punta, no lo agrega: solicita una sincronización. Las
consultas y conexiones salientes se hacen fuera del candado del estado local.
Cada vecino tiene un timeout de 2 segundos; su caída no revierte el minado local.

La sincronización periódica repara mensajes perdidos y permite recuperar nodos
reiniciados o que hayan perdido conectividad. También puede solicitarse
manualmente con `SINCRONIZAR`. Después de adoptar otra cadena se guarda el JSON
local; los demás nodos la descubren en su próxima consulta.

## TCP/IP y mensajes JSON

TCP entrega un flujo de bytes, no un mensaje por `recv`. El protocolo existente
usa un JSON UTF-8 por línea y una solicitud/respuesta por conexión. `readline`
reúne fragmentos hasta el delimitador. Los saltos de línea de descripciones se
escapan dentro del JSON. Hay un máximo de **4 MiB por mensaje**.

```json
{"operacion":"AGREGAR_INCIDENTE","datos":{"tipo":"Malware","descripcion":"Archivo sospechoso","reportado_por":"Ana","severidad":"Alta"}}
```

Respuesta: `{"ok":true,"resultado":...}` o `{"ok":false,"error":"..."}`.

| Operación | Datos | Resultado |
| --- | --- | --- |
| AGREGAR_INCIDENTE | tipo, descripcion, reportado_por, severidad | Incidente cifrado e ID provisional |
| MINAR_BLOQUE | Ninguno | Bloque minado y guardado localmente; propagación encolada |
| VER_CADENA | Ninguno | cadena completa y dificultad local |
| VER_BLOQUE_PROPUESTO | Ninguno | Bloque pendiente o null |
| CAMBIAR_DIFICULTAD | dificultad, entero 0–8 | Nueva dificultad local persistida |
| VER_INCIDENTE | numero_bloque, id_incidente | Detalles descifrados para la vista |
| RECIBIR_BLOQUE | bloque, origen opcional [host, puerto] | aceptado o duplicado; error si es inválido o no enlaza |
| SINCRONIZAR | Ninguno | actualizada y errores por vecino |
| VER_NODOS | Ninguno | Dirección, vecinos, archivo y última sincronización |

Consulta manual desde otra terminal:

```powershell
python -c "from cliente.cliente import Cliente; print(Cliente(puerto=7002).solicitar('SINCRONIZAR'))"
python -c "from cliente.cliente import Cliente; print(Cliente(puerto=7002).solicitar('VER_NODOS'))"
```

## Demostración de sincronización y reinicio

1. Inicia los tres nodos con los comandos anteriores y abre la GUI en 7000.
2. Agrega dos incidentes y mina el bloque propuesto.
3. Espera la propagación y abre la GUI en cada nodo o usa **Servidor** y **Refrescar**.
4. Compara número de bloque, hash, padre, nonce y transacciones. Deben coincidir.
5. Cierra el nodo 7002 con Ctrl+C. Agrega otro incidente y mina en 7000.
6. Comprueba que 7000 y 7001 avanzan y que el JSON de 7002 permanece desactualizado.
7. Reinicia 7002 con su mismo comando y archivo. Espera la sincronización inicial
   o solicita `SINCRONIZAR`; su cadena y JSON deben ponerse al día.
8. Cierra todos los nodos y vuelve a iniciarlos con los mismos comandos. Los
   bloques, Génesis y hashes anteriores deben permanecer idénticos.

Para comparar directamente los tres archivos locales sin imprimir los datos:

```powershell
python -c "import json; from pathlib import Path; c=[json.loads(Path(f'blockchain_{p}.json').read_text(encoding='utf-8'))['cadena'] for p in (7000,7001,7002)]; print('Cadenas iguales:', c[0]==c[1]==c[2]); print('Bloques:', [len(x) for x in c]); print('Puntas:', [x[-1]['hash'] for x in c])"
```

La comparación se hace sobre `cadena`: la dificultad local para el próximo
minado puede diferir si el operador la cambió en uno de los nodos.

## Pruebas automatizadas

```powershell
python -m unittest discover -s tests -v
```

Se conservan las pruebas originales. Las nuevas verifican persistencia, reinicio
sin Génesis nuevo, exactitud de campos, cifrado, validación y rechazos, trabajo
acumulado y desempate, archivos independientes, fallos de disco y nodos apagados,
propagación sin ciclos y sincronización de dos y tres nodos. También hay pruebas
reales de Tkinter, cambio de conexión y argumentos de la CLI.

`tests/test_procesos.py` ejecuta el escenario completo en **tres procesos Python
independientes**, apaga y recupera uno y después reinicia los tres. Reserva tres
puertos libres entre 7300 y 8000; las demás pruebas usan puertos efímeros asignados
por el SO. Esa es la excepción técnica al rango de la CLI, para evitar conflictos
en pruebas. Todos usan claves y archivos temporales y dificultad reducida.
Tkinter necesita un escritorio disponible para sus pruebas de integración.

## Límites de esta versión académica

- No hay consenso bizantino, firmas de usuarios, autenticación de clientes ni
  finalidad: una reorganización válida todavía puede cambiar la rama elegida.
- La dificultad la decide cada operador dentro de 0–8; no hay ajuste automático
  de objetivos ni una política económica contra participantes maliciosos.
- Fernet protege los campos guardados. TCP no usa TLS: solicitudes y detalles
  descifrados viajan en claro. Mantén la demostración en localhost.
- Los nodos de la red usan la misma clave Fernet. En máquinas distintas hay que
  provisionar copias de esa clave fuera del protocolo; nunca se transmite en JSON.
  Conserva la clave junto con los respaldos: sin ella no se recuperan los detalles.
- La sincronización intercambia cadenas completas con el límite actual de 4 MiB.
  No se implementan paginación, descarga por segmentos ni indexación de gran volumen.
- La propagación es eventual, no espera confirmación de todos los pares para
  responder a la GUI. En redes lentas varios timeouts pueden demorar una ronda.
- El candado local incluye minado y guardado para priorizar consistencia. Las
  consultas al mismo nodo esperan si está minando; no es una implementación de alto rendimiento.
- Cada puerto/JSON debe tener un solo proceso escritor. No hay coordinación
  entre dos procesos configurados incorrectamente para usar el mismo archivo.
- Solo se persisten bloques confirmados; los propuestos y recuperados de ramas
  descartadas siguen en memoria hasta minarse. La GUI requiere un nodo iniciado.
