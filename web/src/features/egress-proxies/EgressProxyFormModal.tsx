import { Input, InputNumber, Select } from "@douyinfe/semi-ui";
import { KeyRound, Network, Server, User } from "lucide-react";
import { useEffect, useState } from "react";
import { EGRESS_PROXY_TYPE, EGRESS_PROXY_TYPES } from "../../shared/api/generated/constants";
import type { CreateEgressProxyRequest, EgressProxy, UpdateEgressProxyRequest } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";

type EgressProxyFormValues = CreateEgressProxyRequest;

type EgressProxyFormModalProps =
  | {
      open: boolean;
      mode: "create";
      proxy: null;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: CreateEgressProxyRequest) => Promise<void>;
    }
  | {
      open: boolean;
      mode: "edit";
      proxy: EgressProxy;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: UpdateEgressProxyRequest) => Promise<void>;
    };

const EMPTY: EgressProxyFormValues = {
  proxy_type: EGRESS_PROXY_TYPE.HTTP,
  proxy_host: "",
  proxy_port: 8080,
  proxy_account: "",
  proxy_password: "",
};

function initial(proxy: EgressProxy | null): EgressProxyFormValues {
  if (!proxy) return EMPTY;
  return {
    proxy_type: proxy.proxy_type,
    proxy_host: proxy.proxy_host,
    proxy_port: proxy.proxy_port,
    proxy_account: proxy.proxy_account,
    proxy_password: proxy.proxy_password,
  };
}

export function EgressProxyFormModal({ open, mode, proxy, saving, onCancel, onSubmit }: EgressProxyFormModalProps) {
  const [values, setValues] = useState<EgressProxyFormValues>(() => initial(proxy));

  useEffect(() => {
    if (open) setValues(initial(proxy));
  }, [open, proxy]);

  const submit = async () => {
    await onSubmit({
      proxy_type: values.proxy_type,
      proxy_host: values.proxy_host.trim(),
      proxy_port: values.proxy_port,
      proxy_account: values.proxy_account.trim(),
      proxy_password: values.proxy_password,
    });
  };

  const submitDisabled = (
    !values.proxy_host.trim()
    || values.proxy_port < 1
    || values.proxy_port > 65535
  );

  return (
    <ResourceModal
      open={open}
      title={mode === "create" ? "创建出口代理" : "编辑出口代理"}
      saving={saving}
      submitLabel={mode === "create" ? "创建" : "保存"}
      submitDisabled={submitDisabled}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <label>
        <span>代理类型</span>
        <Select
          prefix={<Network size={16} />}
          value={values.proxy_type}
          optionList={EGRESS_PROXY_TYPES.map((type) => ({ label: type.toUpperCase(), value: type }))}
          onChange={(proxy_type) => {
            if (typeof proxy_type === "string") setValues((current) => ({ ...current, proxy_type }));
          }}
        />
      </label>
      <label>
        <span>代理主机</span>
        <Input prefix={<Server size={16} />} value={values.proxy_host} maxLength={255} required
          autoComplete="off"
          onChange={(proxy_host) => setValues((current) => ({ ...current, proxy_host }))}
        />
      </label>
      <label>
        <span>代理端口</span>
        <InputNumber prefix={<Network size={16} />} value={values.proxy_port} min={1} max={65535}
          onChange={(proxy_port) => typeof proxy_port === "number" && setValues((current) => ({ ...current, proxy_port }))}
        />
      </label>
      <label>
        <span>代理账号</span>
        <Input prefix={<User size={16} />} value={values.proxy_account} maxLength={255}
          autoComplete="off"
          onChange={(proxy_account) => setValues((current) => ({ ...current, proxy_account }))}
        />
      </label>
      <label>
        <span>代理密码</span>
        <Input mode="password" prefix={<KeyRound size={16} />} value={values.proxy_password} maxLength={512}
          autoComplete="new-password"
          onChange={(proxy_password) => setValues((current) => ({ ...current, proxy_password }))}
        />
      </label>
    </ResourceModal>
  );
}
