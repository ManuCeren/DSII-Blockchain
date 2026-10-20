# Blockchain y Wallet de Incidentes de Seguridad

Proyecto académico Python 3.10+ con Tkinter, TCP/IP, Proof of Work y consenso
basado en validación y trabajo acumulado. Conserva la arquitectura original.

## Arquitectura

```text
Administrador de Red (registro automático de N nodos, puertos 7000–8000)
   +-- Nodo 7000 <-- TCP/IP cifrado de pares --> Nodo 7001 <-- ... --> Nodo N
          |
          | TCP/IP cifrado del canal Wallet
          |
   Wallet de Incidentes de Seguridad (GUI → Cliente TCP → Servidor → Blockchain)
```

La Wallet consume servicios del servidor; no crea ni mantiene una Blockchain.
Permite agregar incidentes, consultar cadena, bloques e incidentes, minar la
propuesta, cambiar servidor y refrescar información. El servidor ejecuta el
minado y consulta los campos sensibles para responder a la Wallet.

- `core/`: bloques, incidentes, SHA-256, PoW y validación.
- `cliente/cliente.py`: cliente TCP, sin clave de incidentes ni de persistencia.
- `comunicacion.py`: serialización JSON UTF-8, cifrado autenticado y framing.
- `servidor/servidor.py`: servicio local, validación y confirmación en disco antes de memoria.
- `servidor/persistencia.py`: bloques cifrados e índice de la rama activa.
- `servidor/nodos.py`: propagación, sincronización y reparación periódica.
- `servidor/consenso.py`: comparación por trabajo acumulado.
- `administracion/nodos.py`: procesos y registro automático de vecinos.
- `interfaz/`: GUI de la Wallet y del administrador.

## Instalación y ejecución

```powershell
python -m pip install -r requirements.txt
python -m interfaz.gui_administrador --datos datos
```

Crea los nodos desde el administrador. El registro `datos/red_nodos.json` conserva
su identidad por IP y puerto, dificultad y vecinos adicionales. No hay un número
fijo de nodos: el administrador busca puertos libres entre 7000 y 8000 y actualiza
la malla de los procesos activos sin reiniciarlos. La configuración remota requiere
además el token administrativo de cada proceso; no basta la clave del canal.

Selecciona un nodo y pulsa **Abrir Wallet de Incidentes**, o ejecuta:

```powershell
python -m interfaz.gui_incidentes --host 127.0.0.1 --puerto 7000
```

Entradas compatibles: `python main.py gui`, `python main.py servidor` y
`python main.py consola`, con `--host` y `--puerto`. La consola también usa el
cliente cifrado. El botón **Servidor** cambia la conexión desde la Wallet.

También puedes iniciar nodos manualmente, en terminales diferentes:

```powershell
python -m servidor.servidor --puerto 7000 --datos datos --dificultad 2 --nodo 127.0.0.1:7001
python -m servidor.servidor --puerto 7001 --datos datos --dificultad 2 --nodo 127.0.0.1:7000
```

Cada nodo debe compartir el Génesis inicial (misma dificultad de creación) y la
clave original de incidentes de su red. `--clave` selecciona esa clave; `--datos`
selecciona el directorio de persistencia. Los valores predeterminados conservan
las ubicaciones anteriores en la raíz del proyecto. `--nodo HOST:PUERTO` se puede
repetir. Los servidores manuales no habilitan administración remota por defecto.

## Tres usos separados del cifrado

Se usa Fernet de `cryptography`: cifrado simétrico autenticado. No se usa TLS,
certificados ni criptografía de clave pública. Las claves se generan al azar;
no se incluyen claves en el código ni en mensajes TCP.

| Uso | Clave | Quién la necesita |
| --- | --- | --- |
| Descripción y autor del incidente | `clave_secreta.key` o `--clave` | Solo servidores de la misma red |
| Bloque completo en disco | `nodo_PUERTO/persistencia.key` | Solo ese nodo |
| Solicitudes y respuestas Wallet | `canal_wallet.key` | Wallet y servidores |
| Tráfico entre pares y administración | `canal_nodos.key` | Nodos y administrador |

La Wallet nunca lee la clave de incidentes ni la de persistencia. Recibe los
detalles consultados del servidor por el canal cifrado. Cada bloque se cifra
completo al persistirlo, aunque sus transacciones ya contengan campos cifrados.
Los bloques existentes idénticos se verifican y reutilizan sin volver a cifrar.

Por defecto las claves de canal están en la raíz del proyecto, separadas de
`--datos`. Para otras ubicaciones configura rutas absolutas antes de iniciar
Wallet, administrador o servidores:

```powershell
$env:BLOCKCHAIN_WALLET_KEY = 'C:\claves\canal_wallet.key'
$env:BLOCKCHAIN_NODOS_KEY = 'C:\claves\canal_nodos.key'
```

El primer uso genera la clave ausente mediante publicación exclusiva y atómica.
En máquinas distintas, provisiona previamente copias de la misma clave de canal
por un medio seguro externo a este protocolo. Distribuye solo la clave Wallet
a las máquinas Wallet y reserva la de nodos para servidores y administrador.
Protege estos archivos con permisos del sistema operativo. No regeneres una
clave perdida de incidentes o persistencia: restaura la original y su respaldo.
Los archivos de claves y datos generados están excluidos de Git.

El protocolo realiza objeto Python → JSON → UTF-8 → Fernet → TCP y la operación
inversa al recibir. Cada trama tiene prefijo `wallet:` o `nodos:`, un token Fernet
y salto de línea. El contexto usa una clave independiente; cambiar el prefijo
no convierte un token Wallet en un token de pares. El servidor rechaza por el
canal Wallet `RECIBIR_BLOQUE` y `CONFIGURAR_VECINOS`. Los mensajes JSON sin cifrar
ya no son compatibles: deben actualizarse los clientes y servidores juntos.

El límite de 4 MiB incluye prefijo, expansión del cifrado y delimitador. Se
conservan timeouts y lectura de TCP fragmentado. Un token alterado o con clave
incorrecta se rechaza sin ejecutar la operación; las respuestas de error también
se cifran. No hay protección adicional contra repetición de un mensaje válido
ni identidad individual por Wallet: es un protocolo académico de clave compartida.

## Persistencia por bloque y reinicio

Con `--datos datos`, los archivos quedan así:

```text
datos/
  red_nodos.json
  nodo_7000/
    indice.json                # índice v2: dificultad local y hashes ordenados
    persistencia.key            # separada de los JSON cifrados
    bloques/
      <hash_genesis>.json
      <hash_bloque_1>.json
  nodo_7001/
    indice.json
    persistencia.key
    bloques/
      <hash_genesis>.json
      <hash_bloque_1>.json
```

`nodo_PUERTO/indice.json` es el índice de la rama activa. Toda la persistencia
nueva del nodo queda dentro de su carpeta. Los archivos `blockchain_PUERTO.json`
y `.v1.bak` solo sirven como fuentes de migración o recuperación; después de
publicar el índice nuevo no son necesarios ni se actualizan.
Cada archivo de `bloques/` contiene versión y token cifrado del bloque completo;
su nombre es exactamente el hash real más `.json`. También se guarda el Génesis.
Las propuestas sin minar permanecen en memoria y no se persisten como confirmadas.

Al iniciar, el nodo lee el índice, descifra los archivos por hash y reconstruye
la cadena con `Blockchain.from_dict`. Valida estructura, hash, PoW, secuencia,
Génesis, padres e incidentes usando las comprobaciones existentes. No cambia
hash, nonce, timestamp, hash anterior ni dificultad histórica; no vuelve a minar.
La dificultad local para el próximo bloque se conserva en el índice.

Primero se escriben, vacían y sincronizan los archivos temporales. Los bloques
se publican con enlace exclusivo para impedir sobrescrituras; si ya existen,
se autentican y comparan con el contenido esperado. Un conflicto detiene el
guardado. Finalmente se reemplaza atómicamente el índice. Si falla, la cadena
en memoria no se confirma. Pueden quedar archivos completos no referidos al
índice tras un fallo o una reorganización: no se cargan como rama activa ni se
eliminan automáticamente. El índice permite conservar ramas sin ambigüedad.
La garantía de durabilidad ante corte eléctrico depende además del sistema de
archivos; se usa `fsync` de archivos y publicación atómica.

Guarda juntos el índice, los bloques y la clave de persistencia del nodo, además
de la clave original de incidentes. Un archivo corrupto, bloque faltante o clave
ausente provoca error; no se sustituye silenciosamente por otra cadena.

### Migración del formato anterior

Al iniciar sin `nodo_PUERTO/indice.json`, se acepta el archivo histórico
`blockchain_PUERTO.json`: una cadena v1 o el índice v2 que utilizó la primera
implementación por bloques. Se valida la cadena y la clave de incidentes antes
de publicar atómicamente el índice nuevo dentro de la carpeta del nodo. En v1
se conservan el archivo original y una copia `.v1.bak`; en v2 se conserva el
índice anterior sin modificarlo. Los bloques cifrados existentes se autentican
y reutilizan sin cambiar sus bytes. La migración se anuncia en el registro.

Si se eliminó el índice anterior y solo queda un `.v1.bak`, se permite recuperar
el índice nuevo únicamente cuando ese respaldo describe exactamente todos los
archivos de bloques disponibles y cada bloque cifrado coincide con el respaldo.
Un respaldo desactualizado, bloques adicionales o discrepancias provocan error
sin borrar datos ni escoger una rama arbitrariamente. No se usa un respaldo
para ocultar corrupción de un índice existente. Si faltan todos los índices y
el respaldo, restaura el índice de la rama activa desde una copia segura: los
archivos sueltos pueden incluir ramas descartadas o escrituras no confirmadas.

Una vez creado el índice nuevo, el arranque depende solo de `indice.json`,
`bloques/`, `persistencia.key` y la clave original de incidentes. Los archivos
históricos pueden archivarse fuera del directorio sin afectar los reinicios.
No se borran automáticamente durante la migración. No recuperes manualmente un
índice viejo encima del nuevo: desde entonces el viejo deja de actualizarse.

## Consenso, propagación y demostración

El consenso sigue siendo académico, basado en validación y trabajo acumulado,
con desempate determinista; no es una implementación completa del consenso de
Bitcoin. La dificultad histórica pertenece a cada bloque. Las cadenas recibidas
se validan y comparan antes de adoptarlas, sin volver a minarlas. Los incidentes
de una rama local descartada vuelven a la propuesta cuando corresponde.

1. Crea al menos tres nodos desde el administrador y abre la Wallet en el 7000.
2. Agrega un incidente y mina la propuesta. Comprueba `<hash>.json` en cada nodo.
3. Consulta cadena, bloque y detalle del incidente desde la Wallet.
4. Detén un nodo, mina otro bloque y vuelve a iniciarlo. La sincronización
   periódica recupera bloques perdidos; las cadenas convergen.
5. Cierra y reinicia los nodos con los mismos datos y claves. Comprueba que todos
   los hashes, nonces, timestamps y padres coinciden con los anteriores.
6. Agrega más nodos desde el administrador sin modificar código.

Eliminar un registro administrativo requiere detener el nodo y conserva sus
datos. Registrar otra vez el mismo puerto y directorio permite recuperar su cadena.
Cerrar el administrador detiene sus procesos; no elimina bloques ni claves.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

La suite conserva los escenarios anteriores (ajustando las lecturas del disco
al nuevo formato), pruebas GUI y procesos reales. Incluye archivos por hash,
ausencia de texto plano, propuestas no persistidas, conservación de campos al
reiniciar sin minado, cifrado TCP en ambas direcciones, rechazo de manipulación
y claves incorrectas, migración con copia, PoW inválida, claves perdidas,
propagación, consenso y creación dinámica de cinco nodos. También verifica
reinicios tras eliminar el JSON histórico y el respaldo, migración v1/v2,
recuperación segura del índice y rechazo de respaldos desactualizados.
