CREATE TABLE IF NOT EXISTS customer_identity (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id BIGINT NOT NULL COMMENT '客户实体ID', 
	provider VARCHAR(32) NOT NULL COMMENT '身份供应商', 
	app_id VARCHAR(128) NOT NULL COMMENT '供应商应用ID', 
	subject VARCHAR(128) NOT NULL COMMENT '供应商用户ID/OpenID', 
	union_id VARCHAR(128) COMMENT 'UnionID（不保证提供）', 
	create_time DATETIME NOT NULL COMMENT '绑定UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_customer_identity_subject UNIQUE (provider, app_id, subject), 
	FOREIGN KEY(customer_id) REFERENCES customer (entity_id),
	INDEX `ix_customer_identity_customer_id` (`customer_id`),
	INDEX `ix_customer_identity_union` (`provider`, `union_id`)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;
