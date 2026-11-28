import { useEffect, useState } from "react";

type Props = {
  phase: "envelope" | "fly";
};

type Step = "entering" | "open" | "letterIn" | "closing" | "closed";

export function EnvelopeAnimation({ phase }: Props) {
  const [step, setStep] = useState<Step>("entering");

  useEffect(() => {
    if (phase !== "envelope") return;
    const t1 = setTimeout(() => setStep("open"), 150);
    const t2 = setTimeout(() => setStep("letterIn"), 550);
    const t3 = setTimeout(() => setStep("closing"), 850);
    const t4 = setTimeout(() => setStep("closed"), 1150);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
    };
  }, [phase]);

  const isFly = phase === "fly";
  const isOpen = step === "open" || step === "letterIn";
  const showLetter = step === "letterIn";

  return (
    <div className={`envelope-overlay${isFly ? " envelope-overlay--fly" : ""}`}>
      <div className={`envelope-wrapper${isFly ? " envelope-wrapper--fly" : ""}`}>
        {showLetter && <div className="letter-mini" />}
        <div className={`envelope${isOpen ? " envelope--open" : ""}`}>
          <div className="envelope-body">
            <div className="envelope-body__left" />
            <div className="envelope-body__right" />
            <div className="envelope-body__bottom" />
          </div>
          <div className="envelope-flap" />
        </div>
      </div>
    </div>
  );
}
