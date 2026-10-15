import { useNavigate } from "react-router-dom";
import ravenholtLogo from "../../assets/ravenholt-logo.svg";
import { useAuth } from "../../shared/auth/AuthProvider";
import { LandingContent } from "./LandingContent";

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const consolePath = isAuthenticated ? "/playground" : "/login";

  return <LandingContent logoSrc={ravenholtLogo} primaryAction={{ label: "进入操作台", onSelect: () => navigate(consolePath) }} />;
}
