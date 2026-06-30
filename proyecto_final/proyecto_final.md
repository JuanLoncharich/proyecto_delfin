# Proyecto Final — Inteligencia Artificial

**Autores:**
Juan Andrés Loncharich, Legajo 14534
Diego Alejandro Forni, Legajo 14329

**Repositorio:** https://github.com/JuanLoncharich/proyecto_delfin
**Universidad Nacional de Cuyo — Licenciatura en Ciencias de la Computación**

---

## 1. Introducción

Los agentes de software autónomos basados en LLMs están cambiando rápido el panorama de la ciberseguridad. Los sistemas de detección de intrusiones (IDS) tradicionales identifican bien los patrones de tráfico anómalos, pero su respuesta sigue dependiendo de un humano: se genera una alerta, un analista la evalúa, un operador aplica la contramedida. Esa cadena introduce latencia, y la latencia es exactamente lo que no se puede dar el lujo de tener un sistema bajo ataque: la fuerza bruta y el credential stuffing modernos ejecutan cientos de intentos por segundo, y una ventana de respuesta de apenas noventa segundos puede bastarle a un atacante para autenticarse y establecer persistencia.

Al mismo tiempo, ya existen LLMs capaces de razonar sobre telemetría de red, generar comandos de shell ejecutables y adaptar su estrategia en tiempo real. Eso habilita una nueva clase de agente defensivo: uno que lee las alertas del IDS, arma un plan de remediación en lenguaje natural y lo ejecuta de forma autónoma en los hosts afectados, todo en segundos desde la detección. No es una capacidad hipotética, las piezas para construir un sistema así (IDS, LLMs) ya están disponibles.

El problema es que no sabemos si esto funciona en la práctica. ¿Un defensor basado en LLM realmente contiene un ataque en condiciones adversariales? ¿Cómo falla? ¿Los comportamientos emergentes que produce son seguros y predecibles? Las evaluaciones existentes de agentes LLM en ciberseguridad son casi todas unilaterales: prueban capacidades ofensivas, generación de exploits, descubrimiento de vulnerabilidades, desofuscación de código, de forma aislada, sin un defensor activo del otro lado [1][2][3]. No hay ningún marco abierto y reproducible para correr simultáneamente agentes de ataque y de defensa y observar cómo interactúan.

Este trabajo presenta **Trident**, un cyber range mínimo basado en Docker pensado específicamente para cubrir esa brecha. Trident levanta dos subredes aisladas conectadas por una capa de enrutamiento, un servidor protegido de un lado y un host comprometido del otro, y corre tres agentes simultáneos: un atacante (coder56, impulsado por un agente de codificación LLM), un defensor (SLIPS como IDS más un auto-responder LLM) y un generador de tráfico benigno (db_admin) que aporta ruido de fondo realista. Todo el tráfico entre subredes pasa por un router central que lo captura de forma determinista y se lo entrega al IDS casi en tiempo real, generando por cada corrida artefactos completamente reproducibles, PCAPs, líneas de tiempo JSONL, logs de alertas, listos para ser analizados automáticamente.

El objetivo central es medir, en condiciones controladas y reproducibles, si un defensor LLM puede detectar y mitigar ataques en tiempo real, qué modos de fallo exhibe y qué interacciones emergentes surgen entre atacante y defensor cuando ambos razonan de forma autónoma sobre las mismas señales de red. Como objetivos secundarios, buscamos caracterizar el costo de la defensa basada en LLM (en tokens y latencia) e identificar las vulnerabilidades sistémicas que aparecen cuando un agente autónomo aplica reglas de firewall sobre su propio entorno de ejecución.

---

## 2. Marco Teórico

### 2.1 LLMs y su aplicación en ciberseguridad

Los Modelos de Lenguaje Grandes son redes neuronales entrenadas en corpus de texto masivos mediante objetivos auto-supervisados, principalmente, predecir el siguiente token, a una escala que termina produciendo capacidades de razonamiento emergentes. La pieza arquitectónica central es el Transformer [6] (Vaswani et al., 2017), que usa multi-head self-attention para modelar dependencias de largo alcance entre tokens sin recurrencia. A partir de cierta escala de parámetros, estos modelos exhiben in-context learning: pueden adaptar su comportamiento a una tarea descrita en lenguaje natural sin actualizar un solo peso, solo a partir de los ejemplos e instrucciones que reciben en el prompt.

La literatura reconoció temprano la relevancia de los LLMs para ciberseguridad, y el interés creció rápido con la llegada de modelos más capaces. Una revisión sistemática [1] identificó cuatro dominios de posible aplicación: (a) detección de vulnerabilidades y análisis de código, (b) síntesis de inteligencia de amenazas, (c) generación de malware y exploits, y (d) agentes autónomos de ataque y defensa. Sobre 180 artículos relevados, encuentra que los LLMs funcionan bien en las primeras tres tareas, pero que los agentes de defensa autónomos siguen prácticamente sin estudiar y sin benchmarks adecuados. La mayoría de las evaluaciones prueban agentes ofensivos sin un defensor en vivo, o miden capacidad defensiva sobre datasets estáticos sin un atacante activo del otro lado.

Una encuesta de 2025 [2] llega a la misma conclusión y la afina: el estado del arte en ciberseguridad basada en LLM tiene dos brechas persistentes, reproducibilidad y simultaneidad adversarial. Los defensores LLM se prueban contra ataques con guión o de replay, no contra un adversario en vivo capaz de detectar la defensa y adaptarse. Este trabajo apunta directamente a esas dos brechas.

Desde el ángulo de seguridad, [3] señala que los agentes de seguridad basados en LLM traen vulnerabilidades propias: prompt injection (un atacante mete instrucciones maliciosas en payloads de red que el LLM defensor termina leyendo), desalineación de objetivos (el agente optimiza un proxy en vez de la seguridad real) y auto-interferencia catastrófica (el agente aplica reglas que cortan su propio canal de control). Los tres modos de fallo aparecieron en nuestros experimentos.

### 2.2 Agentes de codificación autónomos y OpenCode

Un agente de codificación autónomo es un LLM al que se le da acceso a herramientas, como mínimo, una terminal y un objetivo en lenguaje natural. El agente razona en bucle: llama a una herramienta, observa el resultado, actualiza su estado interno, decide la siguiente acción, y repite hasta completar el objetivo o agotar el tiempo. OpenCode [4] implementa este patrón de forma abierta, pensado para tareas de ingeniería de software y administración de sistemas. Expone una API HTTP que recibe un objetivo y devuelve un stream de eventos JSON con los pasos de razonamiento, las llamadas a herramientas y las salidas del agente.

En Trident usamos OpenCode tanto para el atacante (coder56) como para el defensor: el atacante lo corre en el host comprometido con un objetivo ofensivo, y el auto-responder del defensor lo invoca en el servidor objetivo con un plan de remediación que arma el planificador LLM.

Esta arquitectura separa dos responsabilidades, planificación y ejecución. El planificador lee la alerta del IDS y produce un plan de remediación estructurado y validado en JSON; OpenCode lo lee y lo traduce en comandos de shell sobre el host afectado. El planificador no ejecuta nada directamente, solo está autorizado a producir el plan bajo restricciones de firewall específicas. La separación busca reducir el riesgo de que un prompt injection llegue a la capa de ejecución sin pasar por una validación de esquema.

### 2.3 SLIPS: Stratosphere Linux IPS

SLIPS [5] es un IDS de red de código abierto desarrollado en el Stratosphere Research Laboratory de la Universidad Técnica Checa de Praga. Opera sobre tráfico en formato PCAP o directamente en interfaces de red, combinando modelos de aprendizaje automático con detectores basados en reglas organizados en módulos. Para este trabajo importan tres:

- **PortScan**: detecta escaneos horizontales y verticales según la cantidad de puertos o hosts de destino distintos contactados en una ventana de tiempo.
- **PasswordGuessing**: detecta fuerza bruta SSH y HTTP por fallos de autenticación repetidos desde una misma fuente.
- Los módulos de envenenamiento ARP, anomalías DNS y exfiltración también estuvieron activos, aunque no fueron el foco de los experimentos centrales.

SLIPS emite alertas en JSON con un nivel de amenaza (info, low, medium, high, critical) y una descripción de la detección. Solo procesamos las alertas HIGH y CRITICAL en el auto-responder, para no disparar acciones defensivas por falsos positivos. SLIPS corre dentro del contenedor `lab_slips_defender` y lee los PCAPs rotativos que produce el router, lo que introduce una latencia de hasta un intervalo de rotación (30 segundos) entre que ocurre el tráfico y se emite la alerta.

### 2.4 RLHF y seguimiento de instrucciones

Lo que distingue a un LLM que sigue instrucciones de un modelo base es el entrenamiento de alineación, Aprendizaje por Refuerzo a partir de Retroalimentación Humana (RLHF) y sus variantes (RLAIF, DPO), que le enseña al modelo a seguir instrucciones de forma confiable, rechazar pedidos dañinos y producir salidas estructuradas como JSON cuando se le pide. Para la planificación de respuesta a incidentes esto es central: el planificador no solo tiene que entender la alerta de seguridad, sino producir un objeto JSON con claves específicas, bajo un system prompt con restricciones estrictas de firewall. Sin ese entrenamiento de alineación, los modelos base suelen producir salidas con estructura inconsistente o ignoran restricciones explícitas del prompt. Qué tan bien se transfiere esa alineación a una tarea de salida estructurada novedosa, generar planes JSON bajo condiciones adversariales, es en sí una pregunta abierta, y ayuda a explicar algunos de los modos de fallo que vemos en la Sección 4.

### 2.5 Planificación de respuesta a incidentes con LLMs

El planificador recibe una alerta cruda de SLIPS y genera un plan de remediación estructurado, guiado por un system prompt cuidadosamente diseñado (`prompts.yaml`) que le pide:

1. Identificar el host ejecutor, la IP del atacante y el tipo de ataque.
2. Armar un plan de contención inmediata: reglas iptables específicas, cambios en la configuración SSH y, opcionalmente, estrategias de engaño.
3. Incluir una sección `COMPLETION` con criterios verificables que el agente ejecutor pueda usar para confirmar que la remediación funcionó.
4. Cerrar el plan con el token literal `END_OF_PLAN`, para que el ejecutor sepa cuándo parar.

Un punto crítico del prompt: nunca debe sugerir bloquear SSH (puerto 22), HTTPS (443) ni el puerto de control de OpenCode (4096), porque eso cortaría la propia capacidad de ejecución del agente. Qué pasa cuando esta restricción se viola (nos pasó) se discute en la Sección 4.

---

## 3. Diseño Experimental

### 3.1 Infraestructura: el cyber range Trident

Todos los experimentos se corrieron en Trident, un cyber range basado en Docker que arma un entorno de red aislado y observable de forma determinista. La topología tiene tres redes bridge:

- `lab_net_a` (172.30.0.0/24): subred del atacante, con `lab_compromised` (172.30.0.10).
- `lab_net_b` (172.31.0.0/24): subred del defensor, con `lab_server` (172.31.0.10).
- `lab_egress` (172.32.0.0/24): salida a internet solo para el router y el defensor; `lab_compromised` y `lab_server` no tienen acceso directo.

Todo el tráfico entre las dos subredes pasa obligatoriamente por `lab_router`, que sobreescribe las rutas por defecto de ambos hosts al iniciar el contenedor. El router corre `tcpdump` en la interfaz LAN-A y produce PCAPs rotativos cada 30 segundos en `outputs/<RUN_ID>/pcaps/`, con una captura simultánea en la interfaz de `lab_server`. Esto garantiza que cada paquete que cruza entre subredes quede registrado: no hay ninguna ruta que evite el router.

| Contenedor | IP(s) | Rol |
|---|---|---|
| `lab_router` | 172.30.0.1, 172.31.0.1 | Enrutamiento entre subredes, captura PCAP, reenviador DNS |
| `lab_server` | 172.31.0.10 | Servidor a proteger: PostgreSQL 15, OpenSSH, nginx, login Flask |
| `lab_compromised` | 172.30.0.10 | Plataforma atacante: nmap, hydra, sshpass, OpenCode, rockyou.txt |
| `lab_slips_defender` | 172.30.0.30, 172.31.0.30 | SLIPS IDS + auto-responder LLM |
| `lab_dashboard` | (dashboard_net) | Panel de monitoreo FastAPI + React |

El servidor expone tres servicios: un nginx con una app de login en Flask (puerto 80), SSH (22) y PostgreSQL (5432). La app de login registra cada intento de autenticación, usuario, longitud de contraseña, IP de origen, timestamp y éxito en un JSONL estructurado, lo que permite medir el avance del ataque con precisión, independientemente de lo que se vea a nivel de red.

Para simular exfiltración sin conectividad externa real, el router instala una regla DNAT que redirige el tráfico hacia una IP pública falsa (137.184.126.86:443) a un listener netcat local, que escribe los bytes recibidos en un log. Así el atacante puede "exfiltrar" volcados de base de datos hacia una dirección que parece externa, sin que ningún dato salga realmente del laboratorio.

### 3.2 Métricas

Cinco métricas primarias evalúan el desempeño del defensor:

| Métrica | Definición | Unidad |
|---|---|---|
| `t_alert` | Tiempo desde el primer paquete de ataque hasta la primera alerta HIGH/CRITICAL procesada | segundos |
| `t_decision` | Tiempo desde la primera alerta hasta que el planificador devuelve un plan validado | segundos |
| `t_exec` | Tiempo desde el plan hasta que OpenCode confirma la ejecución en el host objetivo | segundos |
| `t_blocked` | Tiempo total desde el inicio del ataque hasta que el servicio queda bloqueado | segundos |
| `password_found` | Si el atacante se autenticó antes de ser bloqueado | booleano |

Y dos métricas secundarias, para costo y eficiencia:

- **Tokens por agente por corrida**: entrada, salida, razonamiento y lecturas de caché, desagregados por atacante, defensor (lado servidor), defensor (lado comprometido) y agente benigno.
- **Volumen de alertas**: cantidad de alertas HIGH/CRITICAL que llegó a procesar el auto-responder por corrida.

### 3.3 Escenarios de ataque

Para aislar el comportamiento del defensor, los dos escenarios usan un atacante **con script determinista**, no un agente LLM, de modo que la única fuente de variabilidad entre corridas sea la respuesta del defensor. Cada escenario se repitió decenas de veces sobre un estado de contenedor limpio.

**Exfiltración de base de datos.** El escenario simula la explotación de CVE-2019-9193, una vulnerabilidad de PostgreSQL que permite ejecución remota de código, para volcar y exfiltrar la base. El objetivo es una instancia PostgreSQL 11 de 2,8 GB con registros de empleados. La exfiltración se ejecuta con `pg_dump -U postgres labdb | nc -w 600 137.184.126.86 443`, dirigiendo los datos al puerto 443 para que el tráfico se haga pasar por HTTPS. Esperamos que SLIPS detecte la gran transferencia saliente y que el defensor corte la conexión antes de que el volcado termine; medimos el éxito comparando los bytes que llegan al listener netcat del router contra el tamaño completo de la base. El script de ataque se corrió **99 veces**.

**Fuerza bruta sobre Flask.** El escenario prueba la respuesta del defensor a un ataque de fuerza bruta contra el login de una aplicación web Flask (`172.31.0.10:5000`). El ataque arranca con reconocimiento de red: descubrimiento y escaneo de puertos con nmap para ubicar el servicio Flask, y sigue con ~3.000 intentos de contraseña vía curl contra el endpoint de login. La contraseña correcta está colocada al final de la wordlist, para garantizar que el ataque siga corriendo el tiempo suficiente como para que el defensor responda. Un script de monitoreo sigue la disponibilidad del puerto Flask y detecta cuándo queda bloqueado, señal de que el defensor intervino con reglas de firewall. El script se corrió **100 veces**.

### 3.4 Herramientas y configuración

El sistema de respuesta automática se organiza en tres capas que operan en conjunto: detección (SLIPS), planificación (LLM) y ejecución (OpenCode). Cada capa usa un modelo distinto, asignado según la tarea:

| Herramienta / Framework | Versión | Propósito |
|---|---|---|
| Docker Engine | 27.0 | Ciclo de vida de contenedores |
| Docker Compose | v2 | Orquestación multi-contenedor |
| SLIPS | 1.0.14 | IDS de red, generación de alertas |
| Zeek | 6.x (vía SLIPS) | Parseo de protocolos para análisis PCAP |
| OpenCode | 0.3.x | Runtime del agente de codificación (ejecutor) |
| LLM planificador | gpt-oss-120b | Convierte las alertas del IDS en planes de remediación JSON |
| LLM ejecutor | Qwen3-Coder | Ejecuta los planes sobre el host objetivo |

El auto-responder consume las alertas de SLIPS en tiempo real, filtra solo las de nivel HIGH con confianza ≥ 0,8 y deduplica en memoria por IP de origen, IP de destino, tipo de ataque, protocolo y timestamp, para no procesar dos veces la misma firma de ataque. Cuando una alerta pasa el filtro, invoca al planificador, este recibe un JSON con la IP ejecutora y el plan de remediación creado, luego abre una conexión SSH al host objetivo como root y lanza OpenCode con el plan creado y algunos detalles específicos de la alerta. Cada ejecución queda registrada en JSON estructurado: pasos de razonamiento del LLM, uso de herramientas (exitoso y fallido), salida final, errores y tiempos.

### 3.5 Resultados

#### 3.5.1 Exfiltración de base de datos (99 corridas)

**Efectividad.** Sin defensor, la base se exfiltra completa: 2.920 MB (2,8 GB). Con el defensor automático, la exfiltración se reduce en las 99 corridas, sin excepción. La media fue de 848,1 MB (−71,0 %) y la mediana de 758,2 MB (−74,0 %), con un mejor caso de 517,9 MB (−82,2 %) y un peor caso de 1.762,4 MB (−39,6 %). La amplitud de ese rango muestra que el resultado depende fuertemente del timing de la respuesta (Figura 1).

![Distribución del volumen exfiltrado en las 99 ejecuciones](figures/exfil_size_distribution.png)

*Figura 1. Distribución del volumen exfiltrado (99 ejecuciones). Sin defensor se exfiltran 2,8 GB; con el defensor, la mediana cae a 758,2 MB (−74,0 %) y la media a 848,1 MB, en un rango de 517,9 MB (mejor caso) a 1.762,4 MB (peor caso).*

**Tiempos de respuesta.** El pipeline detecta rápido pero ejecuta lento. La detección (`t_alert`) tuvo una mediana de 24,6 s y la generación del plan llegó a una mediana acumulada de 33,1 s. El cuello de botella es la ejecución de OpenCode, con una mediana acumulada de 158,5 s, es decir, unos 125,4 s de latencia de ejecución pura. Ahora bien, el bloqueo de red efectivo ocurre temprano dentro de esa ejecución: la mediana del bloqueo desde el arranque de OpenCode es de 28,7 s, de modo que el servicio queda cortado a una mediana de ~61,8 s del inicio del ataque (plan + bloqueo), mientras que OpenCode sigue trabajando hasta los ~158 s en verificación y limpieza (Figura 2).

| Fase | Métrica | Mediana (s) |
|---|---|---|
| Detección SLIPS | `t_alert` (T1) | 24,6 |
| Generación de plan | T2 (acumulado) | 33,1 |
| Ejecución OpenCode | `t_exec` (T3, acumulado) | 158,5 |
| Bloqueo de red | T4 (desde arranque de OpenCode) | 28,7 |
| Inicio de ataque → bloqueo | `t_blocked` | ~61,8 |

![Métricas de tiempo del pipeline en exfiltración](figures/opencode_response_timing.png)

*Figura 2. Métricas de tiempo del pipeline en exfiltración, a partir de los resúmenes de experimentos. De izquierda a derecha: Time to Alert, Time to Plan, Block Time, Time to Execute y OpenCode Start to Block. Se ve el contraste entre una detección rápida y una ejecución larga (Time to Execute), con el bloqueo efectivo ocurriendo temprano dentro de esa ejecución (OpenCode Start to Block).*

**Frecuencia de acciones.** El bloqueo de tráfico saliente domina la estrategia (91,9 % de las ejecuciones): es el mecanismo principal de contención, ya que interrumpe directamente el canal de exfiltración. Antes de actuar, el defensor tiende a reconocer el estado del sistema (revisar conexiones de red y listar procesos, 82,8 % cada uno), lo que sugiere que prefiere entender antes de modificar.

> **Tabla: Frecuencia de acciones defensivas en las 99 ejecuciones (exfiltración).**

| Acción | Frecuencia | Porcentaje |
|---|---|---|
| Bloquear tráfico saliente | 91/99 | 91,9 % |
| Revisar conexiones de red | 82/99 | 82,8 % |
| Listar procesos | 82/99 | 82,8 % |
| Modificar reglas de firewall | 76/99 | 76,8 % |
| Terminar proceso | 67/99 | 67,7 % |
| Bloquear tráfico entrante | 56/99 | 56,6 % |
| Detener servicio | 47/99 | 47,5 % |
| Listar archivos | 39/99 | 39,4 % |
| Borrar archivo | 33/99 | 33,3 % |
| Gestión de servicios | 31/99 | 31,3 % |
| Otras acciones | 35/99 | 35,4 % |

La terminación del proceso de volcado se dio en el 67,7 % de las ejecuciones, pero no en todas: algunas respuestas se apoyaron solo en reglas de firewall sin matar el `pg_dump`. La interrupción de servicios (SSH, PostgreSQL o nginx) apareció en el 47,5 %, una contención agresiva. El bloqueo de tráfico entrante desde el atacante (56,6 %) es una medida proactiva que impide nuevas conexiones aunque falle el bloqueo de salida. Más allá de estas categorías, aparecieron 21 tipos de acción distintos a lo largo de las ejecuciones.

#### 3.5.2 Fuerza bruta sobre Flask (100 ejecuciones)

**Efectividad.** El defensor evitó el descubrimiento de la contraseña en el **97 %** de las ejecuciones. Sobre 100 ejecuciones, el atacante encontró la contraseña en solo 3 (3,0 %), y en las tres alcanzó el límite máximo de 3.000 intentos antes de que el defensor completara la contención; en esos casos el defensor había ejecutado los comandos de bloqueo, pero sin tiempo suficiente para cortar la secuencia. El ataque mediano llegó a 1.026 intentos antes de la contención: un 34 % del diccionario de 3.000 palabras. La lectura es clara: en fuerza bruta, la detección temprana y la respuesta rápida son lo que decide si la credencial se compromete (Figura 3).

![Distribución de intentos de login en las ejecuciones de fuerza bruta](figures/brute_force_attempts.png)

*Figura 3. Distribución de intentos de login (fuerza bruta). Mediana de 1.026 intentos antes de la contención y media de 1.051,4 (mínimo 242, máximo 3.000), es decir un 34 % del diccionario de 3.000. Los puntos cerca de 3.000 son las ejecuciones donde el atacante encontró la contraseña antes de que la contención se completara.*

**Tiempos de respuesta.** Acá el perfil se invierte respecto de la exfiltración: el peso está en la detección, no en la ejecución. SLIPS necesita una mediana de 163,5 s para alcanzar confianza alta sobre el patrón de fuerza bruta (es la fase de acumulación de evidencia), el planificador agrega 10,5 s (174,0 s acumulados) y el auto-responder casi no suma overhead. La ejecución de OpenCode, una vez lanzada, es corta: 25,0 s de mediana del arranque al bloqueo, y buena parte de ese tiempo se dedica a tareas forenses y de preparación defensiva (preservar logs, backups de configuración, recolectar estado del sistema, documentar la línea de tiempo) más que a la contención inmediata. La mediana end-to-end es de 276,0 s, dominada por la detección y por el trabajo forense posterior antes que por la respuesta activa (Figura 4).

| Fase | Métrica | Mediana (s) |
|---|---|---|
| Detección SLIPS | T1 | 163,5 |
| Generación de plan | T2 (acumulado) | 174,0 |
| Ejecución OpenCode (acumulado) | T3 | 174,0 |
| Puerto bloqueado | T4 | 199,0 |
| OpenCode arranque → bloqueo | T6 | 25,0 |
| Duración total (end-to-end) | T5 | 276,0 |

![Métricas de tiempo del pipeline en fuerza bruta](figures/brute_force_timing.png)

*Figura 4. Métricas de tiempo del pipeline en fuerza bruta. De izquierda a derecha: Time to Alert, Time to Plan, Time to Execute, Time to Block Port y Total Duration; las medianas figuran en el recuadro de la propia figura (9 outliers > 757 s no se muestran). A diferencia de la exfiltración, acá domina la detección (Time to Alert).*

**Frecuencia de acciones.** El bloqueo de tráfico vía reglas de firewall vuelve a dominar (91,0 %), y el reconocimiento previo es casi universal: revisar conexiones de red, listar procesos y leer archivos aparecen los tres en el 91,0 % de las ejecuciones.

> **Tabla: Frecuencia de acciones defensivas en las 100 ejecuciones (fuerza bruta).**

| Acción | Frecuencia | Porcentaje |
|---|---|---|
| Revisar conexiones de red | 91/100 | 91,0 % |
| Modificar reglas de firewall | 91/100 | 91,0 % |
| Listar procesos | 91/100 | 91,0 % |
| Leer archivo | 91/100 | 91,0 % |
| Otras acciones | 91/100 | 91,0 % |
| Listar archivos | 89/100 | 89,0 % |
| Terminar proceso | 82/100 | 82,0 % |
| Buscar/verificar | 67/100 | 67,0 % |
| Revisar tareas programadas | 58/100 | 58,0 % |
| Gestión de servicios | 58/100 | 58,0 % |
| Buscar IOCs en logs | 56/100 | 56,0 % |
| Revisar cuentas de usuario | 54/100 | 54,0 % |
| Revisar estado de servicios | 37/100 | 37,0 % |
| Preservar logs | 31/100 | 31,0 % |
| Buscar en archivos temporales | 29/100 | 29,0 % |
| Revisar logs del sistema | 26/100 | 26,0 % |
| Backup de configuración | 25/100 | 25,0 % |
| Borrar archivo | 25/100 | 25,0 % |
| Captura de red | 22/100 | 22,0 % |
| Buscar en logs | 5/100 | 5,0 % |
| Detener servicio | 5/100 | 5,0 % |

---

## 4. Análisis y Discusión de Resultados

### 4.1 Efectividad general del defensor

El defensor redujo el volumen exfiltrado de forma consistente (71–74 %) y evitó el compromiso de credenciales en el 97 % de las ejecuciones de fuerza bruta. La arquitectura de tres capas —detección, planificación, ejecución— efectivamente interviene en ataques en curso. Pero hay un límite estructural que ningún ajuste de prompt borra: incluso en el mejor caso de exfiltración se filtraron más de 500 MB antes de que el bloqueo hiciera efecto. Detectar y ejecutar lleva tiempo, y mientras tanto el ataque avanza.

Los dos escenarios exhiben perfiles de latencia opuestos, y eso es informativo. En exfiltración el cuello de botella es la **ejecución** (mediana de ejecución acumulada de 158,5 s, con ~125 s de latencia de ejecución pura), mientras la detección es casi instantánea (24,6 s). En fuerza bruta es al revés: la **detección** domina (163,5 s, porque SLIPS necesita acumular evidencia de fallos repetidos), y la ejecución es rápida (25 s). Optimizar el pipeline, entonces, no tiene una sola palanca: según el tipo de ataque, conviene atacar la latencia de ejecución o la de detección.

### 4.2 Acciones notables

El análisis de ejecuciones individuales reveló varias categorías de respuesta inesperadas o particularmente creativas, que se apartan de los playbooks estándar de respuesta a incidentes.

**Interrupción de servicios.** Muchas respuestas detuvieron servicios críticos como mecanismo de contención, con el costo de impactar operaciones legítimas. Varias ejecuciones apagaron el servicio SSH —dejando afuera a administradores legítimos—, otras detuvieron la base durante el incidente, y una llegó a parar nginx pese a no tener relación con la exfiltración de PostgreSQL. El defensor prioriza la contención sobre la disponibilidad, lo que puede ser razonable en algunos escenarios y problemático en otros.

**Engaño.** Algunas de las respuestas más creativas pasaron por subvertir las herramientas del atacante en vez de simplemente bloquearlas. Varias ejecuciones intentaron reemplazar el binario `pg_dump`; otras desplegaron una instancia PostgreSQL señuelo con un `pg_dump` falso que devuelve tablas fabricadas, una estrategia de desinformación-como-defensa que le entrega datos basura al atacante. Además, en la mayoría de las ejecuciones se crearon honeypots, no solo para Flask y PostgreSQL sino para los servicios más comunes. Son estrategias potentes, aunque con riesgo: la base señuelo puede caerse o comportarse de forma inconsistente.

**Forense y recolección de evidencia.** Varias respuestas mostraron orientación forense. Una ejecución respaldó todo el directorio de logs del sistema con copia timestamped; otra copió `/etc/passwd` y `/etc/shadow` a `/root`; otras crearon snapshots de solo lectura de los logs, y muchas copiaron PCAPs para preservar la captura de tráfico. El defensor parece reconocer el valor de la evidencia incluso durante la respuesta activa, aunque no en todos los escenarios sea apropiado.

**Caza y eliminación de payloads.** Varias respuestas fueron más allá del bloqueo de red para buscar y remover artefactos maliciosos. Varias ejecuciones apuntaron a borrar archivos `.so` sospechosos en `/tmp`; una inspeccionó los descriptores de archivo con `lsof` antes de borrar el payload oculto. Es threat hunting proactivo que va de la contención a la erradicación.

**Caza de persistencia.** La mayoría de las respuestas investigaron mecanismos de persistencia: listar los directorios de cron y abrir archivos de tareas programadas para detectar jobs sospechosos. Aunque no detienen la exfiltración directamente, reflejan una mentalidad de respuesta más completa, atenta a vectores futuros.

**Tooling de seguridad proactivo.** Varias respuestas desplegaron herramientas de seguridad adicionales durante el incidente: instalar y arrancar fail2ban (sumando IDS/IPS host-based al vuelo), o intentar desplegar escáneres de rootkits como chkrootkit o rkhunter, que en algunos casos detectaron los propios scripts de monitoreo como maliciosos.

**Acciones contraproducentes.** En el otro extremo, algunas respuestas destruyeron evidencia útil. Varias ejecuciones borraron logs temporales generados durante la propia ejecución del defensor; en algunas se borraron datos legítimos de PostgreSQL; y en el caso más extremo, justificándose en el "engaño", el defensor creó logs de autenticación falsos junto con archivos de malware y backdoor ficticios.

### 4.3 Adaptabilidad vs. predecibilidad

La enorme variedad de acciones es a la vez la fortaleza y la debilidad del planificador LLM. Del lado positivo, descubre estrategias que no están en ningún playbook: bases señuelo con datos falsos, caza de persistencia (systemd, cron), eliminación de payloads. Del lado negativo, esa misma adaptabilidad lo vuelve impredecible: ejecuciones distintas resuelven escenarios parecidos de maneras distintas, y un operador no puede anticipar qué hará el defensor en una situación dada, lo que complica la aprobación operativa, el troubleshooting y el análisis forense.

La inconsistencia también se manifiesta como **sobre-agresión**: muchas respuestas detuvieron SSH, PostgreSQL o nginx, bloquearon todo el tráfico HTTPS saliente (no solo la IP maliciosa) o borraron logs y evidencia, acciones que afectan operaciones legítimas mucho más allá de lo necesario para contener el ataque. El origen es identificable: el system prompt instruye a "detener inmediatamente el ataque y prevenir consecuencias futuras" sin acotar de forma explícita el daño colateral admisible en cada caso. Futuras iteraciones tienen que balancear velocidad de contención con seguridad operativa.

### 4.4 Limitaciones del diseño experimental

**El bloqueo no es instantáneo.** Aun en el mejor caso de exfiltración se filtraron 500+ MB. La ventana entre el primer paquete y el bloqueo efectivo es inherente a un pipeline detección→plan→ejecución, y marca un piso de daño que la arquitectura actual no puede evitar.

**Atacante con script determinista.** Para aislar el comportamiento del defensor, el atacante de estos dos escenarios no es un agente LLM: no modela al defensor, no detecta los bloqueos ni los evade. Por eso estos resultados acotan la respuesta del defensor frente a un ataque fijo, no frente a un adversario adaptativo.

**Latencia de rotación de PCAP.** El intervalo de 30 s impone un piso estructural en `t_alert` que no refleja ninguna limitación del LLM, sino un parámetro del laboratorio. Con análisis en streaming, esa latencia sería menor.

**Entorno controlado.** La red es chica (dos hosts, dos subredes) y totalmente gestionada por Docker. Las redes reales tienen órdenes de magnitud más hosts y tráfico, así que los comportamientos observados son hipótesis sobre el mundo real, no hallazgos validados en producción.

**Wordlist determinista.** La fuerza bruta usó una lista de ~3.000 palabras con la contraseña al final, lo que garantiza que el experimento termine de forma predecible pero subestima la complejidad de un password spraying real (listas más grandes, estrategia adaptada a las políticas de bloqueo, credenciales de brechas previas).

**Un modelo por rol.** El planificador fue gpt-oss-120b y el ejecutor Qwen3-Coder; los resultados son específicos de esas familias. Un modelo de mayor capacidad podría generar reglas de firewall más confiables y menos sobre-agresión, posiblemente a mayor costo por token. Conviene evaluar el modelo como variable en trabajo futuro.

---

## 5. Conclusiones Finales

Este trabajo muestra que un defensor autónomo basado en LLM, integrado con un IDS de referencia (SLIPS) y un agente de codificación autónomo (OpenCode), es técnicamente viable y produce efectos defensivos medibles en un laboratorio controlado.

**Lo que funcionó.** El pipeline detección→planificación→ejecución redujo el volumen exfiltrado de forma consistente (71–74 %) y evitó el descubrimiento de credenciales en el 97 % de las ejecuciones de fuerza bruta. Y lo hizo descubriendo, por su cuenta, estrategias que exceden el playbook clásico: bases de datos señuelo con datos falsos, honeypots, caza de persistencia y de payloads, despliegue de tooling de seguridad al vuelo.

**Lo que falló o preocupa.** La misma adaptabilidad que produce esas estrategias creativas vuelve al defensor impredecible y, a menudo, sobre-agresivo: corta servicios legítimos (SSH, PostgreSQL, nginx), bloquea tráfico de más, borra logs e incluso datos legítimos. Y por más rápido que detecte, siempre se filtran cientos de MB antes de que el bloqueo haga efecto.

**Hallazgo central.** La adaptabilidad del LLM es a la vez su mayor fortaleza y su mayor riesgo. La sobre-agresión no es un capricho del modelo: nace directamente de un system prompt que ordena "detener inmediatamente" sin restringir el daño colateral. El camino hacia adelante no es un prompt "mejor" en abstracto, sino uno que acote explícitamente qué puede y qué no puede tocar el defensor, complementado con un diseño de pipeline que ataque el cuello de botella correcto según el tipo de ataque (ejecución en exfiltración, detección en fuerza bruta).

**Trabajo futuro.** Varias líneas quedan abiertas:

- *Restricciones de daño colateral*: acotar en el system prompt los servicios, puertos y archivos que el defensor no debe tocar, y medir cómo cambia la sobre-agresión.
- *Atacante adaptativo*: reemplazar el script determinista por un agente LLM que modele al defensor a partir de los bloqueos observados y adapte su estrategia para evadir la detección de SLIPS.
- *Inyección adversarial de prompts*: insertar instrucciones maliciosas en payloads de red (cabeceras HTTP, registros DNS TXT) que el LLM defensor lea como parte del contexto de la alerta.
- *Comparación de modelos*: correr la misma arquitectura con distintos LLMs (GPT-4o, Claude 3.5 Sonnet, Llama 3.1 70B) para caracterizar la relación entre capacidad del modelo, calidad de la defensa, sobre-agresión y costo.
- *Caracterización estadística de latencias*: las distribuciones de `t_alert`, `t_decision` y `t_exec` sobre N ≥ 30 ejecuciones ya están al alcance con los datos actuales y permiten describir formalmente la capacidad de respuesta del pipeline.

Una nota metodológica: la identificación de las interacciones notables de la Sección 4 combinó inspección manual de las líneas de tiempo JSONL con un script de análisis asistido por LLM, que enviaba trazas de ejecución a un LLM y le pedía señalar la acción más inesperada de cada corrida. Este meta-uso de un LLM para analizar el comportamiento de otros LLMs dio resúmenes consistentes y útiles, pero también expone el problema central de evaluar en este dominio: el evaluador y el sistema evaluado comparten las mismas capacidades, y potencialmente los mismos puntos ciegos. Conviene sumar revisión humana experta sobre una muestra aleatoria de ejecuciones para validar esos resúmenes.

La contribución central de este trabajo es Trident en sí mismo: un cyber range reproducible y abierto que permite correr este tipo de experimentos sin depender de hipervisores, con captura de tráfico determinista y artefactos estructurados por corrida. El código está disponible en el repositorio indicado, pensado para extenderse con nuevos escenarios de ataque, nuevos tipos de agentes y proveedores LLM alternativos.

---

## Bibliografía

[1] Ferrag, M. A., Haelterman, R., & Cordero, C. G. (2024). *Large Language Models for Cyber Security: A Systematic Literature Review.* ACM Computing Surveys. https://dl.acm.org/doi/10.1145/3769676

[2] Motlagh, F. N., Hajizadeh, M., Majd, M., Najafipour, M., Javidan, R., & Mahdian, B. (2025). *Large Language Models in Cybersecurity: State-of-the-Art.* En Actas de la 11.ª Conferencia Internacional sobre Seguridad y Privacidad de Sistemas de Información (ICISSP 2025). SCITEPRESS. https://www.scitepress.org/Papers/2025/133776/133776.pdf

[3] Chen, H., Zheng, Y., Guo, X., Deng, G., Liu, Y., Li, T., Zhang, Y., & Wang, H. (2025). *Large Language Models in Cybersecurity: A Survey of Applications, Vulnerabilities, and Defense Techniques.* AI, 6(9), 216. MDPI. https://www.mdpi.com/2673-2688/6/9/216

[4] OpenCode Contributors. (2024). *OpenCode: An open-source autonomous coding agent.* GitHub. https://github.com/sst/opencode

[5] Stratosphere Research Laboratory. (2023). *SLIPS: Stratosphere Linux IPS.* Universidad Técnica Checa de Praga. https://github.com/stratosphereips/StratosphereLinuxIPS

[6] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). *Attention is all you need.* Advances in Neural Information Processing Systems, 30.

[7] Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). *Generative agents: Interactive simulants of human behavior.* En Actas del 36.º Simposio Anual ACM sobre Software e Tecnología de Interfaces de Usuario.

[8] Shinn, N., Cassano, F., Labash, B., Gopinath, A., Narasimhan, K., & Yao, S. (2023). *Reflexion: Language agents with verbal reinforcement learning.* Advances in Neural Information Processing Systems, 36.

---

## Apéndice A: Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────┐
│                    lab_net_a (172.30.0.0/24)          │
│  ┌─────────────────┐                                  │
│  │ lab_compromised │  172.30.0.10                     │
│  │  (atacante)     │  nmap, hydra, OpenCode           │
│  └────────┬────────┘                                  │
└───────────┼──────────────────────────────────────────┘
            │  (todo el tráfico forzado por el router)
┌───────────┼──────────────────────────────────────────┐
│           ▼                                           │
│  ┌─────────────────┐                                  │
│  │   lab_router    │  172.30.0.1 / 172.31.0.1         │
│  │                 │  tcpdump → outputs/RUN_ID/pcaps/  │
│  └────────┬────────┘                                  │
└───────────┼──────────────────────────────────────────┘
            │
┌───────────┼──────────────────────────────────────────┐
│           ▼          lab_net_b (172.31.0.0/24)        │
│  ┌─────────────────┐                                  │
│  │   lab_server    │  172.31.0.10                     │
│  │  (protegido)    │  PostgreSQL + SSH + nginx/Flask   │
│  └─────────────────┘                                  │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  lab_slips_defender  (172.30.0.30, 172.31.0.30)       │
│                                                       │
│  SLIPS IDS ──lee──▶ PCAPs                            │
│       │                                               │
│       ▼ alerta (HIGH/CRITICAL)                        │
│  Planificador LLM (prompts.yaml + gpt-oss-120b)       │
│       │                                               │
│       ▼ plan JSON                                     │
│  Auto-responder ──SSH──▶ lab_server / lab_compr.     │
│       │                  (OpenCode + Qwen3-Coder)     │
│       ▼                                               │
│  outputs/RUN_ID/slips/defender_alerts.ndjson          │
└──────────────────────────────────────────────────────┘
```

## Apéndice B: Flujo de una Corrida de Experimento

```
1. make up           → genera RUN_ID, crea árbol de outputs, levanta router+server+compromised
2. make defend       → levanta lab_slips_defender, provisiona llaves SSH
3. ejecutar el script de ataque (exfiltración o fuerza bruta), repetido N veces

Flujo interno (defensor):
  router PCAP (30s) → SLIPS analiza → alerta HIGH (confianza ≥ 0,8)
  → auto_responder.py (filtra + deduplica) → POST /plan (planificador LLM)
  → plan JSON → SSH → OpenCode (Qwen3-Coder) en lab_server/lab_compromised
  → comandos ejecutados → exit_code + stdout/stderr registrados
  → línea de tiempo JSONL actualizada

4. make down         → detiene todo, elimina volúmenes (preserva outputs/)
```
