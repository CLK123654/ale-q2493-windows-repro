import fs from 'node:fs/promises'; import path from 'node:path'; import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';
const root='/Users/xiaoyu/Documents/ale/repairs/build/2493-current-agent',task=path.join(root,'task'),renders=path.join(root,'workbook-renders');await fs.mkdir(renders,{recursive:true});
const head={fill:'#4B556B',font:{bold:true,color:'#FFFFFF'},wrapText:true},body={wrapText:true,verticalAlignment:'top',borders:{bottom:{style:'thin',color:'#D9DEE8'}}};
function addSheet(book,name,rows,widths){const sheet=book.worksheets.add(name),range=sheet.getRangeByIndexes(0,0,rows.length,widths.length);range.values=rows;range.format=body;sheet.getRangeByIndexes(0,0,1,widths.length).format=head;widths.forEach((w,i)=>sheet.getRangeByIndexes(0,i,rows.length,1).format.columnWidth=w);range.format.autofitRows();sheet.freezePanes.freezeRows(1);sheet.showGridLines=false;}
async function finish(book,label,output){for(const sheet of book.worksheets.items){const preview=await book.render({sheetName:sheet.name,autoCrop:'all',scale:1.25,format:'png'});await fs.writeFile(path.join(renders,`${label}-${sheet.name}.png`),new Uint8Array(await preview.arrayBuffer()));}const errors=await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',options:{useRegex:true,maxResults:100},maxChars:5000});await fs.writeFile(path.join(renders,`${label}.errors.ndjson`),errors.ndjson,'utf8');const structure=await book.inspect({kind:'sheet,table',include:'id,name,values',tableMaxRows:100,tableMaxCols:8,maxChars:45000});await fs.writeFile(path.join(task,`${output}.inspect.ndjson`),structure.ndjson,'utf8');const file=await SpreadsheetFile.exportXlsx(book);await file.save(path.join(task,output));}
const answer=Workbook.create();
addSheet(answer,'交付物答案清单',[
['交付物名称','固定路径/命名规则','用途','判定方式'],
['数据库方案','output/sql/solution.sql','建立事件、日费用、净变化和对账对象','在空数据库执行并检查触发器'],
['本地处理入口','output/tools/build_delivery.py','装载CSV并按批调用psql','在Windows空目录实际运行'],
['最终日费用','output/results/daily_charge.csv','交给计费人员生成账单','按账户、日期和SKU核对'],
['当前事件底账','output/results/usage_event.csv','保存全部更正后的事件状态','按event_id核对'],
['批次摘要','output/results/batch_summary.csv','说明每批三类操作数量和状态','按batch_id核对'],
['净变化记录','output/results/charge_delta_log.csv','回查每批对汇总键的净影响','按batch_id、operation和业务键核对'],
['逐批对账','output/results/batch_reconciliation.csv','记录日汇总与底账重算差异','按batch_id核对'],
['计费说明','output/README.txt','说明交付材料用途与PASS含义','读取正文并与文件互证'],
],[34,76,72,60]);
addSheet(answer,'固定字段答案',[
['交付物或对象','字段路径','正确值','来源与验证'],['daily_charge','主键','account_id、service_day、sku','数据库约束'],['usage_event','quantity类型','numeric14,3','solution.sql'],['usage_event','unit_price类型','numeric14,4','solution.sql'],['daily_charge','amount类型','numeric16,4','solution.sql'],['INSERT触发器','粒度','FOR EACH STATEMENT','PostgreSQL触发器目录'],['INSERT触发器','transition relation','NEW TABLE','solution.sql'],['UPDATE触发器','transition relation','OLD TABLE和NEW TABLE','solution.sql'],['DELETE触发器','transition relation','OLD TABLE','solution.sql'],['全部对账行','status','PASS','底账重算与日汇总键全集比较'],
],[40,56,62,72]);
addSheet(answer,'固定集合答案',[
['交付物或对象','字段或集合','正确集合','判定方式'],['价目表','sku','api_calls、egress_gb、storage_gb','与输入集合匹配'],['更正操作','operation','INSERT、UPDATE、DELETE','集合包含且无其他值'],['日费用业务键','字段','account_id、service_day、sku','主键定义精确匹配'],['净变化度量','字段','delta_quantity、delta_amount、delta_count','表头与数据库列核对'],['逐批对账','字段','missing_group_count、max_quantity_difference、max_amount_difference、status','表头精确匹配'],
],[38,46,100,62]);
addSheet(answer,'固定数值答案',[
['交付物或对象','字段或位置','正确值','容差','来源与验证'],['api_calls','unit_price',0.0250,0.0001,'pricing_catalog.csv'],['storage_gb','unit_price',0.1800,0.0001,'pricing_catalog.csv'],['egress_gb','unit_price',0.0900,0.0001,'pricing_catalog.csv'],['数量结果','逐键差异',0,0.001,'batch_reconciliation.csv'],['金额结果','逐键差异',0,0.0001,'batch_reconciliation.csv'],
],[38,48,34,24,72]);
addSheet(answer,'允许变体答案',[
['对象','允许变化','不可变化','判定方式'],['SQL组织','函数名称、CTE和临时结构可以变化','三类语句级触发器、新旧集合边界和增量语义不能变化','执行触发器并回算'],['批次执行','VALUES或临时表装载可以变化','同批同类操作使用一条数据库语句，batch_order语义不能变化','查看实际SQL与日志'],['CSV结果','行序可以变化','表头、业务主键和字段值不能变化','按业务键排序比较'],['对账','查询结构可以变化','必须做键全集比较并由PostgreSQL重算','构造孤立键并回放'],['计费说明','措辞和段落可以变化','五类结果用途与PASS含义不能写错','与实际文件互证'],
],[34,84,92,64]);await finish(answer,'关键标准答案','关键标准答案.xlsx');
const spec=Workbook.create();addSheet(spec,'任务规格',[
['模块','规格内容'],['任务ID','metering_correction_posting'],['主软件','PostgreSQL Client'],['辅助工具','PowerShell7、Python3.12、UTF-8文本编辑器、CSV查看器和JSON查看器'],['输入来源','订阅计量组提供的事件底账、价目表和已确认更正批次'],['输入获取方式','从交接压缩包解压到Windows11本地目录'],['原始输入文件','usage_events.csv、pricing_catalog.csv、correction_batches.csv和README.txt'],['目标输出文件','output/sql、output/tools、output/results和output/README.txt'],['核心操作链','核对价目与事件→装载数据库→建立语句级变化来源→按批提交更正→合并净变化→维护日费用→逐批底账对齐→整理计费材料'],['计费业务键','daily_charge按account_id、service_day和sku唯一归集quantity、amount与event_count'],['价格选择','初始事件使用价目表，批次中非空unit_price覆盖价目表当前价格'],['语句级变化','同批同类操作一次提交；INSERT读取NEW TABLE，DELETE读取OLD TABLE，UPDATE同时读取旧新集合'],['净变化折叠','billable新事件记正项，旧事件记负项，按计费业务键合并数量、金额与事件数'],['汇总维护','净变化累加到daily_charge，event_count归零的键移除，零变化不写日志'],['批次顺序','按batch_id首次出现顺序处理，批次内batch_order从1连续，操作摘要与输入一致'],['对账边界','每批从usage_event重算billable事件并与daily_charge做键全集比较，记录缺键和最大数值差'],['岗位消费','计费人员使用日费用继续账单生成，用事件底账、净变化和逐批对账解释更正结果'],['完成条件','三类更正均由PostgreSQL语句级触发器处理，每批对账PASS，最终底账与日费用闭合'],['可验证点','触发器粒度、transition relation、批次操作数、价格来源、净变化、零键清理、键全集与数值差'],['不适合作为评分点的内容','SQL排版、函数命名、内部CTE拆分、CSV行序、编辑器、临时目录和说明文字版式'],
],[34,144]);await finish(spec,'任务规格转化','任务规格转化.xlsx');
