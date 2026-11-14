import { z } from "zod";

// 서버(pydantic)와 같은 규칙을 화면에서도 먼저 검사한다. 최종 검증은 항상 서버가 한다.
export const questionSchema = z
  .string()
  .trim()
  .min(2, "질문을 입력해 주세요.")
  .max(500, "질문은 500자 이내로 적어 주세요.");

export const monthSchema = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/, "연월을 선택해 주세요.");

export const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email("이메일 형식을 확인해 주세요.").max(254),
  password: z
    .string()
    .min(10, "비밀번호는 10자 이상이어야 합니다.")
    .max(72, "비밀번호가 너무 깁니다.")
    .regex(/[A-Za-z]/, "영문을 포함해 주세요.")
    .regex(/\d/, "숫자를 포함해 주세요."),
});

export function firstError(result: z.SafeParseReturnType<unknown, unknown>): string | null {
  return result.success ? null : result.error.issues[0]?.message ?? "입력값을 확인해 주세요.";
}
