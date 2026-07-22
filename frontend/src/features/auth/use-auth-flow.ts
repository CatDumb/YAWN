"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useRouter } from "next/navigation";

import {
  normalizeEmail,
  requestOtp as requestOtpCall,
  responseDetail,
  submitAccessRequest as submitAccessRequestCall,
  verifyOtp as verifyOtpCall,
} from "./api";
import { isCurrentUser } from "./contracts";
import {
  accessRequestSchema,
  loginSchema,
  type AccessRequestValues,
  type LoginValues,
} from "./schemas";

export type AuthView = "access-request" | "access-confirmed" | "login";

export const GENERIC_SIGNUP_MESSAGE = "Your access request is pending review.";
export const GENERIC_OTP_MESSAGE =
  "If your account is eligible, a sign-in code has been sent.";
export const OTP_LENGTH = 6;
export const OTP_RESEND_SECONDS = 60;

export function isInvalidSessionStatus(status: number) {
  return status === 401 || status === 403;
}

export function useAuthFlow() {
  const router = useRouter();
  const [view, setView] = useState<AuthView>("access-request");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [otpRequested, setOtpRequested] = useState(false);
  const [resendSecondsRemaining, setResendSecondsRemaining] = useState(0);

  useEffect(() => {
    if (resendSecondsRemaining <= 0) return;
    const timer = window.setInterval(() => {
      setResendSecondsRemaining((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [resendSecondsRemaining]);

  const accessRequestForm = useForm<AccessRequestValues>({
    resolver: zodResolver(accessRequestSchema),
  });
  const loginForm = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
  });
  const accessRequestEmailInput = useWatch({
    control: accessRequestForm.control,
    name: "email",
  });
  const accessRequestFirstNameInput = useWatch({
    control: accessRequestForm.control,
    name: "first_name",
  });
  const accessRequestLastNameInput = useWatch({
    control: accessRequestForm.control,
    name: "last_name",
  });
  const loginEmailInput = useWatch({
    control: loginForm.control,
    name: "email",
  });

  async function submitAccessRequest(values: AccessRequestValues) {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const response = await submitAccessRequestCall(values);
      if (!response.ok) {
        setError(
          await responseDetail(
            response,
            "Unable to submit request. Try again.",
          ),
        );
        return;
      }
      setView("access-confirmed");
    } catch {
      setError("Unable to submit request. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function requestOtpForEmail(email: string) {
    setError(null);
    setNotice(null);
    setOtpError(null);
    setIsSubmitting(true);
    try {
      const response = await requestOtpCall(email);
      if (!response.ok) {
        setError(
          await responseDetail(response, "Unable to request code. Try again."),
        );
        return;
      }
      const data: unknown = await response.json();
      const returnedChallengeId =
        typeof data === "object" &&
        data !== null &&
        "challenge_id" in data &&
        typeof data.challenge_id === "string"
          ? data.challenge_id
          : "";
      if (!returnedChallengeId) {
        setError("Unable to request code. Try again.");
        return;
      }
      setLoginEmail(email);
      setChallengeId(returnedChallengeId);
      setOtpCode("");
      setOtpRequested(true);
      setResendSecondsRemaining(OTP_RESEND_SECONDS);
      setNotice(GENERIC_OTP_MESSAGE);
    } catch {
      setError("Unable to request code. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function requestOtp(values: LoginValues) {
    await requestOtpForEmail(normalizeEmail(values.email));
  }

  async function resendOtp() {
    if (isSubmitting || resendSecondsRemaining > 0 || !loginEmail) return;
    await requestOtpForEmail(loginEmail);
  }

  async function verifyOtp(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setOtpError(null);
    if (!new RegExp(`^\\d{${OTP_LENGTH}}$`).test(otpCode)) {
      setOtpError("Enter the six-digit code from your email.");
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await verifyOtpCall(challengeId, loginEmail, otpCode);
      if (!response.ok) {
        setError(
          await responseDetail(
            response,
            "Invalid, expired, or unavailable sign-in code. Request a new code and try again.",
          ),
        );
        return;
      }
      const data: unknown = await response.json();
      if (!isCurrentUser(data)) {
        setError("Unable to finish sign-in. Try again.");
        return;
      }
      router.replace("/dashboard");
    } catch {
      setError("Unable to verify code. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function setOtpValue(value: string) {
    setOtpError(null);
    setOtpCode(value.replace(/\D/g, "").slice(0, OTP_LENGTH));
  }

  function showLogin() {
    setError(null);
    setNotice(null);
    setOtpError(null);
    setOtpRequested(false);
    setResendSecondsRemaining(0);
    setView("login");
  }

  function showAccessRequest() {
    setError(null);
    setNotice(null);
    setOtpError(null);
    setOtpRequested(false);
    setResendSecondsRemaining(0);
    setView("access-request");
  }

  function showEmailEntry() {
    setError(null);
    setNotice(null);
    setOtpError(null);
    setOtpRequested(false);
    setResendSecondsRemaining(0);
  }

  return {
    accessRequest: {
      emailInput: accessRequestEmailInput,
      firstNameInput: accessRequestFirstNameInput,
      form: accessRequestForm,
      lastNameInput: accessRequestLastNameInput,
      submit: submitAccessRequest,
    },
    error,
    isSubmitting,
    login: {
      email: loginEmail,
      emailInput: loginEmailInput,
      form: loginForm,
      otpCode,
      otpError,
      otpRequested,
      requestOtp,
      resendOtp,
      resendSecondsRemaining,
      setOtpValue,
      showEmailEntry,
      verifyOtp,
    },
    notice,
    showAccessRequest,
    showLogin,
    view,
  };
}

export type AuthFlow = ReturnType<typeof useAuthFlow>;
