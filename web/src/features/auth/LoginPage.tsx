import { Button, Input } from "@douyinfe/semi-ui";
import { Crosshair, KeyRound, Mail } from "lucide-react";
import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { login } from "../../shared/api/systemUsers";
import { showApiError } from "../../shared/api/feedback";
import { useAuth } from "../../shared/auth/AuthProvider";
import { ThemeSwitcher } from "../../shared/theme/ThemeSwitcher";
import ravenholtLogo from "../../assets/ravenholt-logo.svg";

type LoginLocationState = {
  from?: { pathname?: string };
};

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LoginLocationState | null)?.from?.pathname || "/playground";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const response = await login({ email, password });
      if (response.data?.token) {
        signIn(response.data.token);
        navigate(from, { replace: true });
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="lgn">
      <div className="lgn-shell">
        <header className="lgn-top">
          <button
            type="button"
            className="lgn-brand"
            onClick={() => navigate("/")}
            aria-label="返回首页"
            title="返回首页"
          >
            <img src={ravenholtLogo} alt="" />
            <span>RAVENHOLT</span>
          </button>
          <ThemeSwitcher />
        </header>

        <div className="lgn-grid">
          <section className="lgn-col lgn-intro">
            <span className="lgn-eyebrow">AUTHORIZED RED TEAM OPERATIONS</span>
            <h1 className="lgn-h1">
              授权范围内，
              <br />
              把协作做扎实。
            </h1>
            <p className="lgn-lede">
              登录后进入操作台：多智能体编排、项目证据沉淀、可回放时间线，全部收敛在一处。
            </p>
            <dl className="lgn-meta">
              <div>
                <dt>Version</dt>
                <dd className="mono">v0.2.1</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>Kali · Docker · PostgreSQL</dd>
              </div>
              <div>
                <dt>License</dt>
                <dd>仅限授权范围使用</dd>
              </div>
            </dl>
          </section>

          <section className="lgn-col lgn-form-col">
            <h2 className="lgn-form-title">登录控制台</h2>
            <p className="lgn-form-sub">RED TEAM AGENT CONSOLE</p>

            <form className="lgn-form" onSubmit={handleSubmit}>
              <label className="lgn-field">
                <span>邮箱</span>
                <Input
                  size="large"
                  type="email"
                  prefix={<Mail size={15} />}
                  value={email}
                  onChange={setEmail}
                  autoComplete="email"
                  placeholder="请输入邮箱"
                  required
                />
              </label>

              <label className="lgn-field">
                <span>密码</span>
                <Input
                  size="large"
                  mode="password"
                  prefix={<KeyRound size={15} />}
                  value={password}
                  onChange={setPassword}
                  autoComplete="current-password"
                  placeholder="请输入密码"
                  required
                />
              </label>

              <Button
                className="lgn-submit"
                htmlType="submit"
                theme="solid"
                type="primary"
                size="large"
                block
                loading={submitting}
                icon={<Crosshair size={16} />}
              >
                登录
              </Button>
            </form>

            <div className="lgn-credit">
              基于 <a href="https://github.com/usestrix/strix" target="_blank" rel="noopener noreferrer">strix</a> 构建
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
