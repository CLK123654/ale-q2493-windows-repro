from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/"task"
names=["任务名称.txt","任务概要.txt","任务prompt.txt","关键动作.txt","评分表.txt","环境依赖.txt","相关专业软件的关键步骤.txt","task_fields.json","输入数据包.zip","reference.zip","关键标准答案.xlsx","任务规格转化.xlsx","ALE-专家数据作业表_q2493.csv"]
hashes={name:hashlib.sha256((TASK/name).read_bytes()).hexdigest() for name in names}
review={"skill":"humanizer-zh","result":"PASS","reviewed_scopes":["任务名称","任务概要","任务prompt","关键动作","评分表","环境依赖","软件步骤","输入材料中的自然语言","Reference中的用户可见文字","关键标准答案工作簿全部自然语言","任务规格工作簿全部自然语言"],"scores":{"直接性":9,"节奏":9,"信任度":10,"真实性":10,"精炼度":9,"total":47},"minimum_total":45,"notes":["标题改为计量更正批次入账，是计量运营与数据工程共同使用的日常名称，没有Transition Table、跨键补偿、逐批对账审计等术语堆叠。","Prompt从客户申诉引发的月中更正进入，只交代旧费用要回冲、同键变化要合并和计费人员需要什么，没有完整照抄SQL实现处方。","批次数量、事件数量、固定日志行数和最终汇总总量不写入题面，具体批次由输入动态决定，验收关注增量结果与底账重算闭合。","环境提醒使用计量入账最怕的岗位语气，没有本题特有风险是或实现中应等同批模板；所有价格与精度均来自价目表或数据库字段定义。","与当前批次标题交叉复读，未使用交接、审查、排查、冲突处理或双名词后缀；未发现伪引用、虚假SaaS包装、算法炫技或推理断裂。"],"reviewed_artifacts_sha256":hashes,"online_ai_field_used_as_conclusion":False,"reviewed_on":"2026-08-12"}
(TASK/".qa").mkdir(exist_ok=True);(TASK/".qa/humanizer-review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
