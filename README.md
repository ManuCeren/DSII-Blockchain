# Blockchain de incidentes de seguridad informática

Refactor del proyecto original: se conservan las clases, el cálculo SHA-256,
Fernet, el Génesis automático, el bloque propuesto y las vistas de Tkinter.
La diferencia es dónde vive el estado: la GUI y la consola solicitan operaciones
por TCP; únicamente el servidor crea incidentes y modifica la Blockchain.

## Ejecución

Requiere Python 3.10 o posterior, Tkinter y la dependencia de requirements.txt.
Desde la raíz del repositorio:

```powershell
python -m pip install -r requirements.txt
python main.py servidor
```

En otra terminal, después de que el servidor anuncie que está escuchando:

```powershell
python main.py
```

También se conservan `python gui_incidentes.py` y
`python blockchain_incidentes.py` (consola); ambos requieren el servidor iniciado.
La consola también se puede abrir con `python main.py consola`.
El servidor usa 127.0.0.1:5000 y dificultad inicial 4 como el proyecto original.
La GUI mantiene formularios, cadena, detalles descifrados, bloque propuesto,
cambio de dificultad y minado en un hilo para no congelar la ventana.

## Responsabilidades

- `core/encriptador.py`: carga o crea Fernet. La ruta predeterminada apunta a
  `clave_secreta.key` en la raíz, independientemente del directorio de ejecución.
- `core/incidente.py`: representa una transacción y cifra descripción y autor.
- `core/bloque.py`: agrupa incidentes, calcula SHA-256 y busca el nonce con PoW.
- `core/blockchain.py`: mina el Génesis y encadena nuevos bloques.
- `servidor/servidor.py`: servicio de negocio, contador de incidentes, bloque
  pendiente y servidor TCP concurrente. Un candado protege cada operación.
- `cliente/cliente.py`: conexiones y solicitudes; no importa clases de core.
- `comunicacion.py`: codifica y delimita los documentos JSON compartidos.
- `interfaz/gui_incidentes.py`: presentación; usa copias de datos del servidor.
- Archivos originales en la raíz: entradas compatibles y auxiliares de consola.
- `tests/`: pruebas del dominio y comunicación TCP real en puertos temporales.

## Protocolo educativo

TCP es un flujo de bytes: una llamada a recv no garantiza un mensaje completo.
Cada documento JSON termina en un salto de línea; los saltos internos del texto
se escapan dentro de JSON. Se usa UTF-8, un máximo de 4 MiB por mensaje y una
solicitud/respuesta por conexión. El timeout del cliente es configurable.

Solicitud:

```json
{"operacion":"AGREGAR_INCIDENTE","datos":{"tipo":"Malware","descripcion":"Archivo sospechoso","reportado_por":"Ana","severidad":"Alta"}}
```

Respuesta: `{"ok":true,"resultado":...}` o `{"ok":false,"error":"..."}`.

| Operación | Datos | Resultado |
| --- | --- | --- |
| AGREGAR_INCIDENTE | tipo, descripcion, reportado_por, severidad | Incidente cifrado con ID asignado por el servidor |
| MINAR_BLOQUE | Ninguno | Bloque minado; se limpia el propuesto |
| VER_CADENA | Ninguno | cadena y dificultad |
| VER_BLOQUE_PROPUESTO | Ninguno | Bloque pendiente o null |
| CAMBIAR_DIFICULTAD | dificultad (entero 0–8) | Nueva dificultad |
| VER_INCIDENTE | numero_bloque, id_incidente | Detalles descifrados para la vista existente |

Las consultas generales contienen transacciones cifradas. La clave permanece en
el servidor. Los detalles solicitados se descifran allí para mostrarse en la GUI.
Como antes, la cadena está en memoria y se reinicia al cerrar el proceso; la
clave permanece en disco. No se incorporó persistencia de bloques.

## Extensión futura a nodos

`ServicioBlockchain` está separado del transporte TCP y de las vistas. Un futuro
coordinador de nodos deberá validar cadenas candidatas (hash, PoW, enlaces y
reglas de consenso) antes de aplicar cambios bajo el mismo control de concurrencia.
El servicio es el punto de integración para anunciar un bloque ya confirmado;
el JSON de un bloque conserva nonce, timestamps, hashes y transacciones cifradas.
No hay sincronización ni consenso implementados y cada servidor tiene su cadena
local. Antes de distribuir deben acordarse el mismo Génesis, dificultad y reglas
de validación; el Génesis actual conserva su timestamp dinámico original.
El descifrado entre nodos requerirá decidir la gestión de claves.

Esta versión es para localhost: no incorpora autenticación ni TLS. Fernet cifra
los campos almacenados, mientras que TCP transporta en claro solicitudes y
detalles descifrados. No se debe exponer como servicio público sin esas capas.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Se usan claves temporales y dificultad baja para no tocar la clave existente.
Se comprueban Génesis, SHA-256, varias transacciones, PoW, enlaces, rechazo de
agregados y reminado sobre bloques cerrados, cifrado y reutilización de clave.
Las pruebas TCP cubren el flujo completo, Unicode, fragmentación del mensaje,
errores JSON, límites y clientes concurrentes. La protección de los bloques
conserva los métodos del proyecto original: no son objetos Python congelados;
el aislamiento del servidor impide que el cliente modifique esos objetos.
También se comprueba Tkinter con widgets reales y un servidor temporal:
formulario, minado en segundo plano, árbol, detalles descifrados y dificultad.
