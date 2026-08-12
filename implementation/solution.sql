CREATE SCHEMA metering;
SET search_path=metering,public;

CREATE TABLE usage_event(
    event_id text PRIMARY KEY,
    account_id text NOT NULL,
    service_day date NOT NULL,
    sku text NOT NULL,
    quantity numeric(14,3) NOT NULL CHECK(quantity>=0),
    unit_price numeric(14,4) NOT NULL CHECK(unit_price>=0),
    billable boolean NOT NULL
);

CREATE TABLE daily_charge(
    account_id text NOT NULL,
    service_day date NOT NULL,
    sku text NOT NULL,
    quantity numeric(14,3) NOT NULL,
    amount numeric(16,4) NOT NULL,
    event_count integer NOT NULL CHECK(event_count>=0),
    PRIMARY KEY(account_id,service_day,sku)
);

CREATE TABLE charge_delta_log(
    batch_id text NOT NULL,
    trigger_op text NOT NULL,
    account_id text NOT NULL,
    service_day date NOT NULL,
    sku text NOT NULL,
    delta_quantity numeric(14,3) NOT NULL,
    delta_amount numeric(16,4) NOT NULL,
    delta_count integer NOT NULL,
    PRIMARY KEY(batch_id,trigger_op,account_id,service_day,sku)
);

CREATE TABLE batch_reconciliation(
    batch_id text PRIMARY KEY,
    missing_group_count integer NOT NULL,
    max_quantity_difference numeric(14,3) NOT NULL,
    max_amount_difference numeric(16,4) NOT NULL,
    status text NOT NULL
);

CREATE OR REPLACE FUNCTION apply_charge_delta(p_batch text,p_op text,p_rows jsonb)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO metering.charge_delta_log
    SELECT p_batch,p_op,x.account_id,x.service_day,x.sku,x.dq,x.da,x.dc
    FROM jsonb_to_recordset(p_rows) AS x(account_id text,service_day date,sku text,dq numeric,da numeric,dc integer)
    WHERE x.dq<>0 OR x.da<>0 OR x.dc<>0;

    UPDATE metering.daily_charge d
       SET quantity=d.quantity+x.dq,
           amount=d.amount+x.da,
           event_count=d.event_count+x.dc
      FROM jsonb_to_recordset(p_rows) AS x(account_id text,service_day date,sku text,dq numeric,da numeric,dc integer)
     WHERE d.account_id=x.account_id AND d.service_day=x.service_day AND d.sku=x.sku;

    INSERT INTO metering.daily_charge(account_id,service_day,sku,quantity,amount,event_count)
    SELECT x.account_id,x.service_day,x.sku,x.dq,x.da,x.dc
      FROM jsonb_to_recordset(p_rows) AS x(account_id text,service_day date,sku text,dq numeric,da numeric,dc integer)
     WHERE x.dc>0 AND NOT EXISTS(
       SELECT 1 FROM metering.daily_charge d
        WHERE d.account_id=x.account_id AND d.service_day=x.service_day AND d.sku=x.sku
     );
    DELETE FROM metering.daily_charge WHERE event_count=0;
END $$;

CREATE OR REPLACE FUNCTION usage_insert_delta() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rows_json jsonb;
BEGIN
    SELECT jsonb_agg(to_jsonb(x)) INTO rows_json FROM (
      SELECT account_id,service_day,sku,sum(quantity)::numeric AS dq,sum(quantity*unit_price)::numeric AS da,count(*)::integer AS dc
      FROM inserted_rows WHERE billable GROUP BY account_id,service_day,sku
    ) x;
    IF rows_json IS NOT NULL THEN PERFORM metering.apply_charge_delta(current_setting('metering.batch_id',true),'INSERT',rows_json); END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION usage_delete_delta() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rows_json jsonb;
BEGIN
    SELECT jsonb_agg(to_jsonb(x)) INTO rows_json FROM (
      SELECT account_id,service_day,sku,-sum(quantity)::numeric AS dq,-sum(quantity*unit_price)::numeric AS da,-count(*)::integer AS dc
      FROM deleted_rows WHERE billable GROUP BY account_id,service_day,sku
    ) x;
    IF rows_json IS NOT NULL THEN PERFORM metering.apply_charge_delta(current_setting('metering.batch_id',true),'DELETE',rows_json); END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION usage_update_delta() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rows_json jsonb;
BEGIN
    SELECT jsonb_agg(to_jsonb(x)) INTO rows_json FROM (
      SELECT account_id,service_day,sku,sum(dq)::numeric AS dq,sum(da)::numeric AS da,sum(dc)::integer AS dc
      FROM (
        SELECT account_id,service_day,sku,-quantity AS dq,-quantity*unit_price AS da,-1 AS dc FROM old_rows WHERE billable
        UNION ALL
        SELECT account_id,service_day,sku,quantity AS dq,quantity*unit_price AS da,1 AS dc FROM new_rows WHERE billable
      ) d GROUP BY account_id,service_day,sku HAVING sum(dq)<>0 OR sum(da)<>0 OR sum(dc)<>0
    ) x;
    IF rows_json IS NOT NULL THEN PERFORM metering.apply_charge_delta(current_setting('metering.batch_id',true),'UPDATE',rows_json); END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER usage_insert_statement AFTER INSERT ON usage_event REFERENCING NEW TABLE AS inserted_rows FOR EACH STATEMENT EXECUTE FUNCTION usage_insert_delta();
CREATE TRIGGER usage_update_statement AFTER UPDATE ON usage_event REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION usage_update_delta();
CREATE TRIGGER usage_delete_statement AFTER DELETE ON usage_event REFERENCING OLD TABLE AS deleted_rows FOR EACH STATEMENT EXECUTE FUNCTION usage_delete_delta();

CREATE VIEW source_rebuild AS
SELECT account_id,service_day,sku,sum(quantity)::numeric(14,3) AS quantity,sum(quantity*unit_price)::numeric(16,4) AS amount,count(*)::integer AS event_count
FROM usage_event WHERE billable GROUP BY account_id,service_day,sku;
