# Codex 精确本人提醒入口

本机授权调用方可通过目标会话自己的被动回环入口提交一条提醒。入口只接受自身的原生线程 ID 与消息，不提供读会话、工具代理、任意线程选择、模型切换或审批操作。受理不代表模型完成或本人业务处理。

## 目标侧启动

目标本人从 Codex Desktop 原工具环境复工时，用安装 CLI 执行 `paos orient <project> <本人Sxxx> --resume`。Rooter 用 `paos attention rooter-show --resume`。两者读取本人工作上下文并准备同一接收器。只准备接收器的维护命令是 `paos wake prepare-current`。启动或复用回执与 `wake status` 就绪、读信证据分别核对。

底层脚本仍支持维护调用。由目标本人从 Codex Desktop 正常提供的原生工具环境执行人工 prepare：使用已安装 Windows Python，工作目录为安装 Source 的 `scripts`，运行 `python -X utf8 -B codex_receiver_session_start.py --prepare-current`。本入口沿 installation、registry 和 Contact 唯一定位调用者本人的 Home，读取已登记 Python、运行文件和 STOP；不接收目标、pipe 或身份覆盖参数，也不读取伪造的 Hook 事件。

人工 prepare 从原工具环境取得本人线程与 Desktop 连接。已信任的真实 SessionStart 或 UserPromptSubmit 缺终端线程变量时，使用事件 session_id 和同次继承的当前连接；只在本次检查及接收器子进程内传递该身份，全局环境保持。非空工具线程与事件不符即拒绝。两种入口共用唯一 Home、STOP、实例及连接核验和同一启动段。正常 prepare 核已有接收器的正式实例和鉴权/status；已加载共享连接能力且作用域一致时复用，旧接收器按下节的采用合同更新。复用时返回 `receiver_prepare_reused`，不创建子进程或准备日志。需要启动时使用 `CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB`，标准输入关闭，stdout/stderr 仍留原运行文件旁。`CREATE_NO_WINDOW` 只隐藏控制台；当宿主 Job 允许 breakaway 时，第二个标志使新接收器脱离该工具 Job。[Microsoft 进程创建标志](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)及[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)说明了这一机制。

旧receiver未加载共享连接能力，或旧模式下当前Owner连接已更换时，正常prepare在原锁内用既有精确启动调用、OS实例与鉴权空消息拒绝核本人旧服务，再经原Windows实例停止入口退休它；随后同一正常启动段沿原locator归档旧登记并加载当前Owner环境。接收器身份/连接证明未知、STOP、身份变化或缺原Owner环境时保留原服务，明确报receiver_connection_unknown，不回退或循环重试。逐次打开旧pipe不等于其名称会更新。

宿主拒绝创建时只尝试一次，输出 `receiver_prepare_unavailable` 及原错误，人工命令以非零状态退出；不改 Job 策略，不重试或换启动路径。环境缺失、未登记、歧义或 STOP 仍明确停止。创建成功只报告启动器 PID；随后读正式 `wake status` 确认就绪。正常 prepare 与 SessionStart 复用已加载当前连接能力的健康实例；缺该能力的旧进程须沿准确本人核验加载新行为。登记迁移不加载代码。

接收器行为代码需要更新时，由本人在同一个 Desktop 工具环境、安装 Source 的 `scripts` 目录运行 `python -X utf8 -B codex_receiver_session_start.py --update-current`。本入口仍只解析本人的 Home，不接受 PID、Thread、pipe 或目标覆盖。它在原 native 锁内核准确 runtime-file/stop-file、OS 实例和既有鉴权空消息拒绝，再用同一 Windows 进程句柄核创建标识后停止旧被动接收器。STOP、未知、外 Thread、无法鉴权或实例变化时保留原状。旧登记留给正常 prepare 归档，新进程沿原 locator 与 STOP 启动；不要求操作者拼终止命令，不由 Rooter 代管他人实例。

更新后读正式 `wake status`：须有新 receiver 的已核 OS 实例、`prepared=true`，且 `receiver_behavior=native_followup`。此标记由实际发布运行文件的新接收器写入；只迁旧登记不会添加它。启动器 PID、磁盘代码已更新或旧实例 prepared 都不能代替加载确认。只更新需要载入接收器行为的实例；调用方单独更新传输错误分类不要求重启所有接收器。

入口不接受 pipe、caller 或目标 ID 参数。手动入口继承启动者自己的 `CODEX_THREAD_ID` 与 `CODEX_APP_TOOLS_PIPE_PATH`；真实 Hook 可用宿主事件本人身份和其当前连接，接收器仍绑定同一线程。不得从别人进程/文件提取或复制这些值来启动。它内部使用已存在的 Desktop app-tools 客户端，只查询本人状态，再向本人线程发送。不能用另起 CLI/app-server 的会话冒充 Desktop 线程。

Installed communication details are documented in System/Guide; this receiver only accepts its own registered session.

## 应用连接更新与空闲接收器

默认Windows正式版使用应用级app-tools管道。本人准备通过Home和STOP检查后，在安装Data的`runtime-injection/codex-desktop/transport.json`发布当前应用连接。该单一原件记录规范化CODEX_HOME作用域、管道、准确宿主PID及创建实例，不记录caller/session或账号令牌。当前仅支持默认userData的OpenAI.Codex正式包。显式其他userData或其他产品明确返回receiver_prepare_skipped及未支持原因，不发布、不启动或退休接收器，但业务Hook继续读取原文；这不表示提醒就绪。不同CODEX_HOME作用域、未知或不一致错误仍明确失败。

发布者只检查真实事件／本人终端继承的那条已知管道。GetNamedPipeServerProcessId取得服务PID，再核正式包可执行文件与OS创建实例。发布锁内重新核当前连接；旧宿主仍活而出现另一个同域宿主时保留原件并报歧义。旧宿主退出后，新真实事件可原子发布新连接。同一宿主更换管道时，仅在准确旧管道已确认不存在、新管道属于同一实例时更新；两个管道都有效报歧义，旧管道查不明则保留错误。已失效旧管道的延迟事件无法通过锁内核验，不比较mtime猜最新。

加载新行为的被动接收器，在处理一条新请求前读取这一原件，核作用域与实际服务实例，再查询和提醒自己的固定原生线程。另一名同事的真实事件可以发布新应用连接，空闲目标随后使用该连接，目标的caller/session、HTTP授权和STOP继续保持。原生结果未知时不重发，也不再挑另一条连接尝试。

本人正常准备读取实际接收器的鉴权`/status`。旧进程缺共享连接能力时，沿已有准确实例与鉴权拒绝核验退休，并由同一原Owner正常启动新进程；STOP或身份未知时保留。已具备能力且作用域／原件路径一致的进程直接复用，即使它最初捕获的是旧应用连接，也由每次新请求读取当前连接。新进程状态返回`application_transport=true`及实际作用域／原件定位。Rooter据实际状态记录成员采用范围；未产生本人事件的旧进程仍属未加载，不以磁盘包更新代替采用。

没有任何新真实事件或本人准备时，尚无可验证的新连接；应用离线、不同作用域或产品拒绝目标访问时，明确返回不可用。正常Hook已经看到新连接时，空闲接收器可以按次接回；不需要轮询服务或逐个唤醒目标模型。

## 外部提交合同

私有运行文件为 `paos-codex-self-reminder/v1`：`endpoint`、`session_id`、随机 `token`、`pid`、`process_identity`、`receiver_behavior`。进程实例来自receiver自身的OS：Windows为GetProcessTimes创建FILETIME，Linux为boot_id与/proc启动tick。使用真实os.getpid，不使用启动器或venv redirector的PID。`receiver_behavior=native_followup`标明已加载宿主跟进行为，不是授权、queue或业务完成证明。只绑127.0.0.1临时端口。

本人正常prepare验证原Desktop环境、准确self/Thread与STOP。同Thread有效grant只有在正向进程不存在、或OS实例/精确receiver启动调用确定失配时才归档旧文件，在原locator发布新入口。无关同号进程不被终止或接管。实例相符的活receiver、查询未知、无权限、外Thread与STOP均不覆盖。prepare与sender复用原native锁，服务循环不持锁，不需要rebind。

缺process_identity的旧登记不再仅凭pid_alive显示prepared。旧登记先核OS实际启动参数是否符合已安装的 `python -X utf8 -B -m wakeup_native.codex_receiver --runtime-file ... --stop-file ...` 合同；runtime-file与目标stop-file都须按规范化路径或samefile核为同一位置。任一参数确定失配可由本人正常prepare归档恢复；参数无法读取或任一路径无法确定则unknown，不发迁移探测。不会将进程名、文件mtime或端口可达当作实例身份。

旧receiver若仍按原合同运行，读面保持legacy_identity_unverified。本人正常prepare在原锁内，用旧token向原/send提交准确self与空message；既有协议在任何Desktop状态/模型调用前返回HTTP400/invalid_request，授权不符为401、错self为403。只有已核调用参数、该授权响应，以及验证前后相同OS创建实例都成立，才先保留旧原字节为`.legacy-*`，原子添加身份字段，保留原PID/endpoint/token和现有服务。生命周期追加identity_migrated。本次prepare启动器可正常退出；应从正式status看原receiver已迁移，不能把启动器PID当新服务。

空消息验证失败、超时、实例变化或STOP出现时保留原登记，不重启旧进程、不发布另一个入口。旧HTTP服务正处理在途提交时，验证可能超时；待该自然提交结束后由原Owner正常prepare，不重投业务。OS权限/执行位置无法核定时，从原Owner正常Windows入口恢复或交Rooter查准确失败，禁止force、手改grant或借凭据。自定义启动方式不作为已安装调用合同的替代。

`wake status`复用Contact读面，不发HTTP/原生探针。prepared要求PID与OS实例相符；process_identity_mismatch可同时是pid_alive=true/prepared=false。本地身份未验证或查询失败为unknown；这不等于目标失配。实际提醒的发送方不再用调用方OS查询决定是否发送：读取runtime grant后，先向目标已鉴权的`GET /status`核对`session_id`与`process_identity`，再`POST /send`；目标在自身进程内自证身份并回执`process_identity`。旧receiver无`/status`、缺少身份或身份不匹配时确定不发送，不用调用方查询权限兜底，也不换路径。WSL沿登记Windows执行入口核Windows实例，不把Windows PID当Linux PID。启动参数只在旧登记判定时读取，不进入读面、回执或日志。

一次提醒明确区分receiver_offline（陈旧死进程或连接明确拒绝）、receiver_not_prepared（未登记/无有效grant）、native_busy、native_stopped、native_rejected与delivery_uncertain。使用协议error_code而非错误字符串猜状态；Windows子回执和两CLI保留原因、负责Owner、动作及retry=false。未知仍accepted=null，不自动换路或重发。

`GET <endpoint>/status`，请求头同样是 `Authorization: Bearer <本人入口授权>`，返回 `session_id`、目标自身 `pid`、`process_identity`及已加载的`desktop_connection_id`；不读取消息、Desktop、token 或调用方凭据。连接标记由receiver实际捕获的Windows pipe定位作规范化后计算不可逆摘要，只用于与当前Owner定位比较，不代替鉴权或OS实例验证，不公开原始pipe。私有运行文件格式保持原样。旧服务缺连接标记时返回明确unknown，由原Owner按已接受代码正常`--update-current`一次加载，不手工补grant字段。

`POST <endpoint>/send`，请求头 `Authorization: Bearer <本人入口授权>`，JSON 恰为 `{"session_id":"<目标本人>","message":"<一次提醒>"}`。两者都在原生调用前拒绝错目标；`/send` 成功回执还带同一 `process_identity`，供发送方确认状态核验与提交仍是同一 OS 实例。多余字段、空消息或不匹配身份都拒绝；不接受 model/caller/tool/method/pipe 参数。调用方不持有 Desktop 凭据，不能向入口索取历史或调用其他工具。

目标状态明确为active、idle或notLoaded时，入口向既有 `send_message_to_thread` 提交一次已授权提醒；未知状态仍在提交前拒绝。它不传queue、model或设置覆盖，宿主决定如何处理跟进。成功为 HTTP 200、`accepted:true`、准确 `session_id`、`completed:false`，并含 `native_status_before_submit`。该字段只是提交前观察，不保证加入当前turn或下一turn排队。[官方提示说明](https://learn.chatgpt.com/docs/prompting#steering-and-queuing)区分两者；App Server的turn/steer不是本入口调用合同。

STOP为409；缺原生状态为503；发送后无法确认回执为502 `delivery_not_confirmed`、`retry:false`。入口不自动重发、不轮询Mail/Notice、不记录业务attempt；公共调用方也不得在不确定发送后切换路径再次提交。既有已拒绝或不确定的旧提醒不因本行为更新而自动重放。

S032 公共接线使用显式 `receiver_runtime_file` 选择此路径。未配置时沿原同源调用合同；已选择入口后发生错误就返回错误，不降级到另一发送方式。公共错误映射由公共作者负责。

## WSL调用Windows接收器

Windows接收器的`127.0.0.1`由Windows执行端访问。共享runtime文件的路径映射不改变调用者的回环网络位置。需要从WSL调用时，在现有Contact的extension中明确登记`execution_environment: "windows"`和`windows_python: "<已安装Windows Python的绝对.exe路径>"`，保留原receiver_runtime_file、Thread和STOP；不按失败结果临时换路。缺省或`local`仍使用当前进程环境，不根据盘符、端口、网关或连通性猜测执行位置。

显式Windows选路只支持带receiver_runtime_file的Codex本人入口。WSL一次启动已登记Windows Python，执行安装描述符source_root下的scripts/runtime_injection.py；message和最小target合同经UTF-8 stdin交接，不落临时文件或argv，不传Desktop pipe/caller凭据。不以WSL_DISTRO_NAME标签作为执行能力判据；按显式配置实际调用，OSError明确返回执行不可用，不探测、不fallback、不换Source路径。Windows子进程持有Windows原生锁、重新核STOP及准确self grant，再执行一次POST。当前进程已在Windows时不再启动另一个包装进程。执行环境不是身份，也不改变模型或授予别的Thread权限。

进程启动失败直接报错；启动后超时、损坏或目标不符的回执，以及本人receiver的HTTP502 delivery_not_confirmed，均抛InjectionUncertain，禁止重发或切回WSL。独立工具对此输出accepted=null、uncertain=true、retry=false；agent send --remind与wake trigger返回state=delivery_uncertain、accepted=null、retry=false。连接明确拒绝、授权、busy、STOP和前置条件拒绝保持确定拒绝，其他未确认响应不能当作未送达。

agent send的runtime_wake_performed只聚合本次调用：有确证受理成员为true；没有确证但存在未知成员为null；没有提醒或全部确定未执行才为false。每位成员的reminders保留各自真值，Mail持久投递、原生受理、本人消费及业务结果分别记录。成功的accepted只证明原生受理，不证明目标消费或业务完成。

## 生命周期诊断

接收器在运行文件旁追加 `<运行文件名>.lifecycle.jsonl`，记录 UTC 时间、PID，以及 `starting`、`ready`、`exit`。启动记录包含父PID和Python路径，就绪记录包含本人Thread和回环地址；退出记录只保存正常返回或异常类型、已定义错误码，不保存异常正文、消息、token或Desktop pipe。每条记录立即flush，历史记录保留；启动/退出生命周期日志写入失败直接报错。

正常发送方为每次实际HTTP调用生成32位十六进制 `request_id`，通过 `X-PAOS-Request-ID` 头传给receiver，原生payload仍只有session_id/message，不将编号、异常或凭据放入模型消息。缺少该头时receiver只生成本地关联编号；它不是授权或去重凭据。成功技术回执包含request_id；错误回执的diagnostic只包含request_id、phase、exception_type、errno/winerror、http_status和native_status等机器字段，WSL→Windows回包保留这些字段。状态拒绝的`native_status`为`systemError`、`not_returned`（宿主未返回状态）或`unrecognized`（宿主返回协议未识别值）；不复制原始状态文本。异常自由文本不进入diagnostic。调用方进程查询失败时，`wake status`与原生回执保留`phase=process_query`、`operation`、`reason`、`winerror/errno`及异常类型；调用方查询能力不足归`caller_installation_owner`，目标已退出或实例确实失配仍归`target_owner`，未知不在POST前冒充目标问题。

同一生命周期日志按该编号记录 `request_received`、`status_read_started/returned`、`native_submit_started`、`native_result_returned/unknown`、`request_rejected` 及 `http_reply_returned/failed`，附本次请求起算的elapsed_ms。native_submit_started只表示开始调用原生发送封装，不证明其中某个底层pipe请求已被受理；http_reply_returned只表示本端写入返回，不证明调用方收到。回写断连只记机器错误，不重复原生发送。请求诊断日志写入失败时，在既有stderr写request_log_failed与机器错误；不改变已发生的提交结果、不重投，也不因此停止接收器。

调用方HTTP等待失败仍为delivery_uncertain/accepted=null/retry=false；diagnostic.phase=http_wait不指认底层原生阶段。只有同request_id的已有receiver事件才能进一步定位。字段与日志仅改善后续定位，不恢复历史unknown，也不建立队列或自动接续。采用需原Owner加载已接受的新receiver代码；仅替换磁盘文件不能使在跑的旧进程产生新阶段记录。

正常返回和传播到服务外层的Python异常会留下退出记录；强制终止、宿主结束或系统故障可能没有退出记录。只有启动/就绪记录而进程已不存在时，退出原因仍未知，应结合目标本人保留的stdout/stderr及Windows事件检查，不归因父PID消失，不自动重启。STOP是发送栅栏，不会自行结束接收器。日志不改变runtime授权格式或公共prepared判定。

## SessionStart接线

用户级宿主事件定义供已登记的Codex Home使用，不含逐Agent参数。`scripts/codex_receiver_session_start.py`处理SessionStart的startup/resume/compact及UserPromptSubmit：两类事件使用真实session_id并继承当前CODEX_APP_TOOLS_PIPE_PATH；CODEX_THREAD_ID非空时必须与事件相符，缺失时仅在本次本人准备和子进程使用事件身份。它沿既有installation和`ProjectRegistry.read`读取五字段登记的Home适配视图及准确root的Contact，以及安装描述rooter_home的Rooter Contact；Rooter沿公开合同使用`rooter-001`身份和既有rooter_home校验，目录名可以不同，不创建Project Session，也不要求存在Project登记目录。旧schema、缺失或空root的坏项目登记明确失败，不把当前目录当root。当前Thread须在Project与Rooter之间唯一匹配一个已登记且存在的Home；使用该Contact原有receiver_runtime_file、stop_file和windows_python做一次隐藏prepare。环境缺失、未登记、歧义、Home缺失或STOP存在均明确停止，不建身份、不改Contact、不借凭据。

UserPromptSubmit用于本人真实输入前的正常准备，保证后续自然回合也有准备时点；不读取、记录或转发事件中的prompt。健康实例复用，失效实例仍由原锁内的正常prepare判定与归档。脚本支持该事件不等于本机已经安装对应定义；Rooter须在宿主受支持设置中把同一已安装命令接入UserPromptSubmit，并对当前精确定义完成正常审阅和真实触发读回。没有新增轮询、重投、Harness启动或模型调用。

Install SessionStart hooks through the supported host settings; this source does not ship a machine-specific installed hook definition.

An installed hook must be checked on its own host; source files and prior adoption reports are not proof of current trust.

## 正常复工与宿主接线

正常复工入口的 `--resume` 调用同一 `prepare_current`，校验请求的登记工位属于本人。健康且同连接的接收器直接复用，失效或换连接沿原正常路径处理。`receiver_preparation` 保留恢复结果。状态查询保持只读。

宿主Hook可提供自动准备，但不是正常复工的唯一执行面。[官方Hooks说明](https://learn.chatgpt.com/docs/hooks)区分本地编排与云编排，后者不加载本机command Hook。定义已信任与当前会话真实执行必须分别核实；没有事件证据时保留未知，不用合成stdin、配置存在或手工准备证明自动恢复。

## 接线验收限制

官方支持上述SessionStart事件，非managed新定义必须review/trust，信任与当前定义关联：[官方Hooks说明](https://learn.chatgpt.com/docs/hooks)。本机2026-10-15只读配置已有SessionStart信任记录，不能将未见恢复归因于Human未配置；记录存在也不替代当前定义被宿主接受及事件实际执行的证据。需要审阅时通过受支持的产品入口（官方CLI为`/hooks`），不写信任缓存、不用bypass。真实Desktop startup/resume是否触发已安装Hook并继承本人环境，仍须原会话实际观察。

恢复入口为原Owner从当前Desktop工具环境执行“目标侧启动”的 `--prepare-current`，以及宿主真实SessionStart startup/resume/compact或UserPromptSubmit事件。事件定义须已安装、正常信任且继承本人环境；均须随后读正式wake status确认prepared/pid_alive，启动PID或文件存在不能代替就绪。人工模式不合成宿主事件；Hook从标准输入处理真实事件，安装定义由Rooter维护。

常驻观察应核具体工具Job的成员，以及创建工具结束、后继自然回合中的正式状态。嵌套Job可能仍有外层归属；不能仅因 `IsProcessInJob(..., NULL)` 为true就反复停止活实例。脱离工具Job不等于持续自愈，也不承诺Desktop退出、注销或重启后的可用性。历史缺exit的退出原因仍未知；自然正式来件的受理与业务消费另核，不盲发测试提醒。

切回已加载聊天时，是否收到 SessionStart 由宿主决定。UserPromptSubmit 对应实际输入。存在真实事件和当前 Desktop 连接时，Hook 直接运行本人准备；已加载共享连接能力的空闲接收器可在新请求前采用同作用域其他真实事件发布的连接；仍在运行的旧版进程不能据此判为已采用。如果 SessionStart 到达脚本而缺少 Desktop 环境，已登记的会话会在 `additionalContext` 收到本人的 `--resume` 入口。接收器生命周期日志的 `owner_hook_entered` 保存事件、SessionStart 的 source 和环境可用性，不含 prompt、管道地址或凭据。退出原因取真实退出记录。

压缩后同一根会话的 `SessionStart(source=compact)` 也进入本人接收准备，沿原 Thread、Contact 与 STOP 检查；健康实例复用，旧连接沿已有本人校验处理。安装时将该脚本的 SessionStart matcher 设为 `^(startup|resume|compact)$`，按宿主正常入口审阅变更；源码更新不会自动修改本机 Hook 或信任记录。`clear`、`fork` 仍不在该接收准备合同内。普通 Stop 不表示业务完成，本脚本不在 Stop 重启接收器。

这只覆盖宿主已派发事件后的接收准备，不代表压缩后业务上下文已读或阶段交付已完成。云编排不执行本地 command Hook 时，继续用本人 ENTRY 的显式复工入口；原生支持范围见 [Hooks](https://learn.chatgpt.com/docs/hooks#hooks-with-cloud-orchestration)。

## 验证

Receiver behavior is exercised by the current source tests; historic Dashboard tests are not part of this checkout.

准备Hook只核已知管道的OS宿主、作用域与已鉴权receiver的实际能力，不反向调用Desktop工具或读取线程状态；宿主正在等待Hook完成时，准备路径不能再等待同一宿主。原生线程可用性仍由正常一次提醒在发送阶段判断。
