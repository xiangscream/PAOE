"""Two reading layers in Markdown; keep metadata and the original reference intact."""
import re

HUMAN_START = '<!-- paoe:human-intro:start -->'
HUMAN_END = '<!-- paoe:human-intro:end -->'
AGENT_START = '<!-- paoe:agent-reference -->'
HEADER_END = '<!-- paoe:reading-header:end -->'

SYSTEM_INTROS = {
    'HOME.md': ('这是你的 PAOE 工作入口。想推进一件事，先打开它的项目；想找一种做法，去共享方法库。系统说明、项目资料和方法正文各有自己的位置，这里帮你找到它们。', '从下面的导航选择你现在想做的事。'),
    'Architecture/SYSTEM-MAP.md': ('这张图解释 PAOE 的几部分怎样配合：项目保存事情的资料，工位保存 Agent 的当前工作，共享库保存做事的方法，程序负责把它们连接起来。', '先顺着图看一遍，再到项目或方法入口打开实物。'),
    'Architecture/DATA-OWNERSHIP.md': ('同一件事只在一个地方维护，才能避免出现几份互相矛盾的版本。这页告诉你：项目成果、待办、方法和机器配置分别应该改在哪里。', '准备修改文件时，先在下面的表里找到它属于哪一类。'),
    'Architecture/MODULE-MAP.md': ('想了解“输入一条命令后，程序做了什么”，可以从这里找对应代码。先追一条你用过的命令，比一次读完所有源码更容易理解。', '先找你关心的功能，再打开它对应的程序文件。'),
    'Installation/CURRENT-MACHINE.md': ('这是本机安装的位置表。需要找程序、配置文件或请人排查安装问题时，可以直接用这里的真实路径。', '平时使用 PAOE 可以回到首页；维护安装时再查下面的路径和命令。'),
    'Installation/PATHS.md': ('PAOE 的程序、共享方法和项目可以分别存放。几份配置文件负责记住这些位置，所以你从不同目录打开系统，也能找到同一份资料。', '想查这台电脑实际放在哪里，打开 [[CURRENT-MACHINE|本机安装]]。'),
    'Projects/PROJECT-INDEX.md': ('这里列出你明确登记给 PAOE 管理的项目。电脑里有一个资料文件夹，并不代表它自动成为 PAOE 项目。', '在下面找到项目，再打开它原来的入口文件。'),
    'Agents/AGENT-DIRECTORY.md': ('每位 Agent 都有自己的工位，用来保存工作入口和当前待办。这里帮你找到这些工位；具体任务仍在成员自己的文件中。', '按项目和成员找到对应入口；安装维护问题可找 Rooter。'),
    'Agents/ROOTER.md': ('Rooter 是负责这套环境的维护者。安装、共享库位置、联系入口或唤醒出了问题，可以交给 Rooter；项目做什么仍由项目负责人安排。', '下面说明 Rooter 的工位位置和联系方法。'),
    'Libraries/RESOURCES.md': ('这是共享方法库的目录入口。工作流讲一件事怎样推进，技能讲某类专业工作怎样做，工具说明讲有什么工具可用。链接会打开独立方法库中的原文件。', '按下面的 Workflow、Skill、Tool 分类选择你需要的内容。'),
    'Libraries/WORKFLOW.md': ('工作流相当于做事的路线：接到任务后怎样开始、怎样交付、卡住时找谁。指南和模板则提供具体操作与格式。', '到 [[RESOURCES#Workflow|工作流原件]] 找到适合当前事情的做法。'),
    'Libraries/SKILL.md': ('技能是某类专业工作的做法，例如写产品文档、分析技术资料、制作图表。你可以先了解它能帮什么，再让 Agent 按后面的专业步骤执行。', '到 [[RESOURCES#Skill|技能原件]] 选一份打开；正文在独立的 PAOS-Libraries 库。'),
    'Libraries/TOOL.md': ('这里帮你了解工具能做什么、从哪里使用。工具说明中提到某项能力，还需要结合本机安装和账号权限判断能否实际调用。', '先在 [[RESOURCES#Tool|工具目录]] 找用途，再查看对应工具的使用说明。'),
    'Runtime/CONTACT.md': ('Agent 的工位是保存工作的地方，Codex、OpenCode 等应用是它实际运行的地方。唤醒就是把新的工作提醒送到已经安排好的会话。', '遇到“有邮件但没动静”时，用这页分清是文件、联系还是运行问题。'),
    'Frontend/BOARD.md': ('画板是一个可选的图形视图，方便查看项目和成员关系。日常阅读资料可以直接用 Obsidian；需要图形视图时再打开画板。', '下面给出启动方式；链接只有在本机服务运行后才可打开。'),
    'Operations/DAILY-USE.md': ('日常只需围绕一件具体事情开始：找到项目，说明希望完成什么，把结果留回项目。需要专业做法时，再去共享方法库找。', '从 [[../Projects/PROJECT-INDEX|项目入口]] 选一件要推进的事。'),
    'Operations/RECOVERY.md': ('文件打不开、项目找不到或 Agent 没有响应时，先确认是哪一部分出了问题。原资料通常还在，先查位置和运行状态，再决定怎样修。', '把打不开的入口、提示和预期结果交给对应负责人；下面有定位方法。'),
    'Operations/BACKUP.md': ('系统说明、项目资料、共享方法和程序是几类不同的内容。备份时要分别照顾到它们，才能在换电脑或误改后恢复。', '先确定这次要保护哪类内容，再按下面的边界备份。'),
    'Learning/ROADMAP.md': ('这是一条从会用 PAOE 到看懂实现的学习路线。先认识本机几部分，再追踪一条实际命令，逐步理解程序怎样找到并处理文件。', '从你正在使用的功能开始，把问题和理解记到 [[NOTES/README|个人笔记]]。'),
    'Learning/NOTES/README.md': ('这里放你自己的学习笔记、疑问和实验记录。可以用自己的话写，不必写成系统指南。', '在这个文件夹新建普通 Markdown 笔记，并链接到你正在学习的资料。'),
}

WORKFLOW_INTROS = {
    'guide-asd-ste100': '这份指南用于需要严格、统一表达的技术文档。它帮助减少歧义，让不同读者对同一句说明得到相同理解。',
    'guide-concise-writing': '这份指南帮助把话写清楚：先说结果或动作，一句表达一件事，保留真正影响决定的条件。写消息、指南和汇报时都可以用。',
    'guide-document-editing': '要写或修改一份文档时，先从这里选择合适的方法：日常表达、技术写作或某种专业文档各有对应入口。',
    'guide-paos-cat-operations': '这是一份日常操作手册。需要给成员发工作、查看处理情况或排查联系问题时，可以在这里找到具体步骤。',
    'guide-paos-interface-reference': '这里是命令和字段的参考手册。已经知道要做什么、需要确认准确参数时，再查对应条目。',
    'guide-project-work-world': '这份指南说明资料、成果和经验应该放在哪里，以及什么时候记录版本。它帮助你和 Agent 维护一份容易找到的项目资料。',
    'guide-research-consultation': '遇到需要查资料或请别人判断的问题时，这份指南帮助说明背景、提出具体问题，并把得到的结论用回原任务。',
    'guide-rooter-installation': '这是系统维护者的工作说明。程序安装、共享库位置和成员运行入口出问题时，Rooter 按这份指南定位和处理。',
    'guide-runtime-handoff': '当一个 Agent 需要换会话或交给另一位执行者时，这份指南帮助保留已有成果，并交清楚下一步。',
    'guide-tool-pitfalls': '这里收集实际使用工具时遇过的限制和处理方法。碰到相似问题时查对应条目，可以少走一次弯路。',
    'guide-upgrade-adoption': '新版本通过测试后，还要决定本机怎样采用、出了问题怎样回退。这份指南把发布和本机更新的步骤分开讲清楚。',
    'guide-work-method': '不确定该用哪种方法做事时，从这里开始。它按任务用途带你找到合适的工作流、技能和工具说明。',
    'ops-entry': '已经知道要做什么、只想找到操作入口时，查这张导航。具体命令和步骤会链接到对应说明。',
    'wf-agent-work-cycle': '这份工作流说明 Agent 接到任务后怎样持续推进：先了解现有工作，按需找方法或同事，保存成果，再接着完成总体目标。',
    'wf-coordinator-governance-cycle': '协调者负责把项目目标、成员分工和验收对齐。这份工作流说明怎样让每项工作有人推进、结果有人接续。',
    'wf-meeting-audio-package': '日常对话、会议和录音里常混着事实、想法和待办。这份工作流帮助保留原始材料，再把有用内容整理到项目和当前任务中。',
    'wf-night-maintenance': '一天工作结束后，可以按这份流程整理当天成果、修正当前入口，并留下第二天能够接着做的线索。',
}

SKILL_INTROS = {
    'architecture-diagram':'把系统各部分及其关系画成容易讨论的架构图，支持网页预览和可继续编辑的图文件。',
    'build-teaching-slides':'把教学内容组织成有节奏的网页课件，同时照顾页面、讲稿和离线交付。',
    'clean-writing':'把文档写得清楚、自然，去掉空话和重复表达，同时保留事实、条件和必要说明。',
    'cpp-pro':'处理 C++ 程序的开发、调试和性能问题，适合需要专业编程判断的任务。',
    'daily-work-summary':'把一天零散的笔记、进展和交付整理成清楚的日总结，让你看到完成了什么、卡在哪里。',
    'dispatching-parallel-agents':'在你明确需要多人并行时，判断哪些工作能独立分给不同 Agent，并把结果汇合。',
    'docx-safe-editing':'修改已有 Word 报告时，照顾目录、标题、编号和版式，减少改正文时破坏文档结构的问题。',
    'extract-report-essence':'从长报告中提炼管理者需要的结论、依据和待决定事项，同时保留完整原文供追溯。',
    'feishu-cli':'通过已配置的命令行入口读写飞书文档；执行前需要对应文档的访问权限。',
    'feishu-doc-edit':'处理飞书文档中的具体编辑任务，让内容修改和实际文档结构保持一致。',
    'ffmpeg-video-clip':'对视频进行截取、拼接或转码，按所需片段和交付格式处理媒体文件。',
    'fullstack-dev':'处理网页应用前后端相连的开发任务，从界面到接口一起检查。',
    'grill-me':'通过连续追问检验一个想法或方案，把隐藏的假设和还没想清楚的问题找出来。',
    'handoff':'把当前任务交给下一位执行者时，说明现状、已有成果、未决问题和下一步。',
    'playwright-browser-automation':'用浏览器自动化完成或验证网页操作，适合需要重复执行的页面任务。',
    'ppt-polish':'改善已有演示文稿的视觉层次、版面和表达，让重点更容易被看到。',
    'pptx-animation-injector':'为已有 PowerPoint 文件添加或调整动画，配合演示顺序表达内容。',
    'product-definition-research':'围绕产品定义查资料、比较方案，帮助判断目标用户、场景和产品方向。',
    'product-definition-workbench':'把分散的产品研究、想法和决定整理成清楚的工作台，找到当前定义和下一项关键决定。',
    'product-feature-mining':'从用户、市场、竞品和技术能力中寻找有价值的功能，并整理成产品主线。',
    'product-function-tree':'把产品功能按层级画成结构图，让范围、分类和功能之间的关系更清楚。',
    'project-progress-sync':'把成员上报的进展、问题和下一步整理到项目中，并据此形成日更或周报。',
    'skill-engineering-change':'修改代码、配置或依赖时，按影响范围安排验证和采用，让工程变更有明确结果。',
    'skill-independent-review':'由独立复核者检查候选成果是否满足约定，并指出具体问题和接受条件。',
    'software-business-process-analysis':'把软件里的用户操作、状态、数据和异常处理连起来，弄清完整流程。',
    'spec-writing':'把产品要求写成研发和测试可以执行的规格，明确行为、条件和验收方式。',
    'technical-research':'学习和调查专业技术时，梳理概念、来源和结论，分清已确认的事实与待验证的判断。',
    'vault-scribe':'把访谈、会议、想法和零散笔记整理成符合现有 Obsidian 库习惯的文章或记录。',
    'write-prd':'把产品想法和研究结果写成可供研发、测试使用的需求文档，说明用户、功能和验收方式。',
}


def add_intro(text, explanation, next_step):
    """Insert after the title; leave every original character outside the header unchanged."""
    if HUMAN_START in text:
        if not all(marker in text for marker in (HUMAN_END, AGENT_START, HEADER_END)):
            raise ValueError('Incomplete reading header; review the existing document')
        return text
    offset = 0
    if text.lstrip('\ufeff').startswith('---'):
        front = re.match(r'\ufeff?---\r?\n.*?\r?\n---(?:\r?\n|$)', text, re.S)
        if not front:
            raise ValueError('Unclosed frontmatter')
        offset = front.end()
    title = re.search(r'(?m)^# [^\r\n]+(?:\r?\n|$)', text[offset:])
    if title is None:
        raise ValueError('Document needs an existing level-one title')
    position = offset + title.end()
    nl = '\r\n' if '\r\n' in text else '\n'
    header = nl.join(['', HUMAN_START, '> [!info] 给使用者', '> '+explanation,
                      '>', '> **从这里开始：** '+next_step, HUMAN_END, '',
                      AGENT_START, '## 操作与参考', HEADER_END, ''])
    return text[:position] + header + text[position:]


def system_page(text, name):
    return add_intro(text, *SYSTEM_INTROS[name])


def remove_intro(text):
    """Used by adoption checks to prove the original reference is preserved."""
    start = text.index(HUMAN_START)
    # add_intro inserts one blank line before the marker and one newline after end.
    nl = '\r\n' if '\r\n' in text else '\n'
    start -= len(nl)
    end = text.index(HEADER_END) + len(HEADER_END) + len(nl)
    return text[:start] + text[end:]
