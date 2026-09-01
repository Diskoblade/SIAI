import { useRef, useState } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { ArrowDown, ArrowRight, ArrowUpRight, LockKeyhole, Network, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

const vendorLabels = [
  "UPLOAD_DATA.exe",
  "ASK_ANYTHING",
  "INSTANT_AI",
  "FREE_CONTEXT",
  "MODEL_ACCESS",
  "AUTO_INSIGHT",
  "AI_CLOUD_24H",
];

const architectureNodes = [
  ["01", "AUTH", "AUTH_OK"],
  ["02", "IDENTITY", "USER_03"],
  ["03", "DEPARTMENT", "RESEARCH"],
  ["04", "VECTOR STORE", "PRIVATE"],
  ["05", "RETRIEVAL", "SCOPED"],
  ["06", "LOCAL MODEL", "READY"],
  ["07", "RESPONSE", "CITED"],
];

const reveal = {
  hidden: { opacity: 0, y: 36 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

function SectionLabel({ number, children, inverse = false }) {
  return (
    <div className={`si-section-label${inverse ? " si-section-label--inverse" : ""}`}>
      <span>{number}</span>
      <span>{children}</span>
      <span>SYS_{number}</span>
    </div>
  );
}

function BrutalButton({ to, children, variant = "light" }) {
  return (
    <Link className={`si-button si-button--${variant}`} to={to}>
      <span>{children}</span>
      <ArrowUpRight size={18} strokeWidth={2.5} aria-hidden="true" />
    </Link>
  );
}

export default function LandingPage() {
  const heroRef = useRef(null);
  const reduceMotion = useReducedMotion();
  const [accessMode, setAccessMode] = useState("private");
  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ["start start", "end start"],
  });
  const imageY = useTransform(scrollYProgress, [0, 1], [0, reduceMotion ? 0 : 90]);
  const headlineX = useTransform(scrollYProgress, [0, 1], [0, reduceMotion ? 0 : -70]);

  return (
    <main className="landing">
      <header className="si-nav">
        <a className="si-wordmark" href="#top" aria-label="SIAI home">
          <strong>SIAI</strong>
          <span>SOVEREIGN INTELLIGENCE</span>
        </a>

        <nav className="si-nav__links" aria-label="Landing page sections">
          <a href="#market">01 PRODUCT</a>
          <a href="#security">02 SECURITY</a>
          <a href="#architecture">03 ARCHITECTURE</a>
          <a href="#retrieval">04 RETRIEVAL</a>
        </nav>

        <div className="si-nav__actions">
          <Link className="si-login" to="/login">LOGIN</Link>
          <Link className="si-enter" to="/signup">
            ENTER SI <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </header>

      <section className="si-hero" id="top" ref={heroRef}>
        <motion.img
          className="si-hero__image"
          src="/assets/siai-market-hero.png"
          alt="A lone visitor faces a vast, concrete marketplace of AI data machines."
          style={{ y: imageY }}
        />
        <div className="si-hero__shade" />
        <div className="si-hero__status">
          <span>SIAI / SI / 2026</span>
          <span className="si-status-dot">MARKET_ACTIVE</span>
          <span>COORD: 28.6139 / 77.2090</span>
        </div>

        <motion.div
          className="si-hero__headline"
          initial={reduceMotion ? false : { opacity: 0, x: -80 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          style={{ x: headlineX }}
        >
          <p>THE AI MARKET / OPEN 24H</p>
          <h1>
            AI IS<br />
            EVERYWHERE.<br />
            <span>TRUST IS NOT.</span>
          </h1>
        </motion.div>

        <div className="si-hero__vendors" aria-label="Fictional AI market services">
          {vendorLabels.slice(0, 4).map((label, index) => (
            <motion.span
              key={label}
              initial={reduceMotion ? false : { opacity: 0, x: index % 2 ? 24 : -24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 + index * 0.08, duration: 0.35 }}
            >
              {label}
            </motion.span>
          ))}
        </div>

        <a className="si-hero__scroll" href="#market">
          ENTER THE MARKET <ArrowDown size={18} aria-hidden="true" />
        </a>
      </section>

      <section className="si-market" id="market">
        <SectionLabel number="01">MARKET</SectionLabel>
        <div className="si-market__grid">
          <motion.div
            className="si-market__statement"
            variants={reveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.25 }}
          >
            <p className="si-kicker">EVERY PROMISE HAS A PRICE.</p>
            <h2>FASTER.<br />CHEAPER.<br />SMARTER.</h2>
          </motion.div>

          <div className="si-vendor-wall">
            {vendorLabels.map((label, index) => (
              <motion.div
                className={`si-vendor si-vendor--${(index % 3) + 1}`}
                key={label}
                initial={reduceMotion ? false : { opacity: 0, scale: 0.92 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ delay: index * 0.04, type: "spring", stiffness: 240, damping: 20 }}
              >
                <span>VENDOR_{String(index + 1).padStart(2, "0")}</span>
                <strong>{label}</strong>
                <small>{index % 2 ? "UPLOAD EVERYTHING" : "ZERO FRICTION"}</small>
              </motion.div>
            ))}
          </div>
        </div>
        <div className="si-ticker" aria-hidden="true">
          <div>FREE CONTEXT / MODEL ACCESS / UPLOAD EVERYTHING / WHO OWNS THE MEMORY? / </div>
        </div>
      </section>

      <section className="si-leak" id="security">
        <SectionLabel number="02" inverse>LEAK</SectionLabel>
        <div className="si-leak__headline">
          <motion.h2
            initial={reduceMotion ? false : { clipPath: "inset(0 100% 0 0)" }}
            whileInView={{ clipPath: "inset(0 0% 0 0)" }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.6, ease: [0.77, 0, 0.18, 1] }}
          >
            DATA<br />MOVED.
          </motion.h2>
          <p>WITHOUT<br />CONTROL.</p>
        </div>

        <div className="si-transfer">
          {["CLIENT_04", "CONFIDENTIAL_STRATEGY.PDF", "VENDOR_03", "VENDOR_08", "UNKNOWN"].map((item, index) => (
            <div className={index === 1 ? "si-transfer__node si-transfer__node--file" : "si-transfer__node"} key={item}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{item}</strong>
              {index < 4 && <ArrowRight size={28} strokeWidth={2.5} aria-hidden="true" />}
            </div>
          ))}
        </div>

        <div className="si-leak__meta">
          <div><span>OWNER</span><strong>UNKNOWN</strong></div>
          <div><span>ACCESS</span><strong>MULTIPLE</strong></div>
          <div><span>STATUS</span><strong>EXPOSED</strong></div>
          <div><span>REVOCATION</span><strong>UNAVAILABLE</strong></div>
        </div>

        <motion.p
          className="si-leak__manifesto"
          variants={reveal}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
        >
          YOUR DATA SHOULD NEVER BECOME <span>SOMEONE ELSE&apos;S ADVANTAGE.</span>
        </motion.p>
      </section>

      <section className="si-escape">
        <div className="si-escape__commands" aria-hidden="true">
          <span>EXIT</span><span>REVOKE</span><span>DISCONNECT</span><span>LEAVE MARKET</span><span>TAKE CONTROL</span>
        </div>
        <motion.h2
          initial={reduceMotion ? false : { x: "-18%", opacity: 0 }}
          whileInView={{ x: 0, opacity: 1 }}
          viewport={{ once: true, amount: 0.5 }}
          transition={{ type: "spring", stiffness: 120, damping: 16 }}
        >
          SO<br />WE<br /><span>LEFT.</span>
        </motion.h2>
      </section>

      <section className="si-reveal" id="architecture">
        <SectionLabel number="03" inverse>SI</SectionLabel>
        <div className="si-reveal__intro">
          <div className="si-reveal__mark">SI</div>
          <motion.div
            variants={reveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.35 }}
          >
            <p className="si-kicker">SOVEREIGN INTELLIGENCE</p>
            <h2>YOUR DATA.<br />YOUR INTELLIGENCE.<br /><span>YOUR CONTROL.</span></h2>
          </motion.div>
        </div>

        <div className="si-architecture">
          <div className="si-architecture__header">
            <span>PRIVATE_INFRASTRUCTURE / BUILD_SEQUENCE</span>
            <span>STATUS: ONLINE</span>
          </div>
          <div className="si-architecture__flow">
            {architectureNodes.map(([number, title, state], index) => (
              <motion.div
                className="si-architecture__item"
                key={number}
                initial={reduceMotion ? false : { opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.5 }}
                transition={{ delay: index * 0.08, type: "spring", stiffness: 220, damping: 22 }}
              >
                <div className="si-node">
                  <span>NODE_{number}</span>
                  <strong>{title}</strong>
                  <small>{state}</small>
                </div>
                {index < architectureNodes.length - 1 && <ArrowRight className="si-node__arrow" size={24} aria-hidden="true" />}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="si-collaboration">
        <SectionLabel number="04">ACCESS</SectionLabel>
        <div className="si-collaboration__copy">
          <h2>WORK<br />TOGETHER.</h2>
          <h2 className="si-red">LEAK<br />NOTHING.</h2>
        </div>

        <div className="si-zone">
          <div className="si-zone__label"><LockKeyhole size={16} aria-hidden="true" /> SI_SECURE_ZONE</div>
          <div className="si-zone__users">
            {["USER_01", "USER_02", "USER_03"].map((user, index) => (
              <motion.div
                className="si-user-node"
                key={user}
                initial={reduceMotion ? false : { opacity: 0, scale: 0.85 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1 }}
              >
                <span>IDENTITY</span><strong>{user}</strong><small>AUTH_OK</small>
              </motion.div>
            ))}
            <Network className="si-zone__network" size={44} strokeWidth={1.5} aria-hidden="true" />
          </div>
          <div className="si-zone__boundary"><span>TRUST_BOUNDARY</span><span>ENCRYPTED</span></div>
          <div className="si-zone__external"><span>EXTERNAL</span><strong>ACCESS_DENIED</strong></div>
        </div>
      </section>

      <section className="si-control">
        <SectionLabel number="05" inverse>CONTROL</SectionLabel>
        <div className="si-control__layout">
          <div>
            <p className="si-kicker">ACCESS_CONTROL_05</p>
            <h2>PERMISSION<br />IS PHYSICAL.</h2>
          </div>

          <div className="si-switchboard">
            <div className="si-switchboard__tabs" role="group" aria-label="File access mode">
              <button
                type="button"
                className={accessMode === "private" ? "is-active" : ""}
                aria-pressed={accessMode === "private"}
                onClick={() => setAccessMode("private")}
              >
                PRIVATE
              </button>
              <button
                type="button"
                className={accessMode === "department" ? "is-active" : ""}
                aria-pressed={accessMode === "department"}
                onClick={() => setAccessMode("department")}
              >
                DEPARTMENT
              </button>
            </div>
            <div className="si-switchboard__readout" aria-live="polite">
              <div><span>FILE</span><strong>STRATEGY_2026.PDF</strong></div>
              <div><span>OWNER</span><strong>USER_03</strong></div>
              <div><span>ACCESS</span><strong>{accessMode === "private" ? "01 PERSON" : "FINANCE / 07 USERS"}</strong></div>
              <div><span>STATE</span><strong>{accessMode === "private" ? "ACCESS_PRIVATE" : "DEPT_FINANCE"}</strong></div>
            </div>
          </div>
        </div>
      </section>

      <section className="si-query" id="retrieval">
        <SectionLabel number="06">RETRIEVAL</SectionLabel>
        <div className="si-query__heading">
          <p className="si-kicker">ASK YOUR ORGANISATION</p>
          <h2>KNOWLEDGE.<br />WITH PROOF.</h2>
        </div>

        <div className="si-terminal">
          <div className="si-terminal__bar">
            <span>QUERY_001</span><span>AUTHENTICATED</span><span>DEPT: RESEARCH</span><span>SOURCES_ALLOWED: 03</span>
          </div>
          <div className="si-terminal__prompt">
            <span>&gt;</span>
            <p>What decisions were made about Project Aurora?</p>
          </div>
          <div className="si-terminal__status"><span>RETRIEVAL_COMPLETE</span><span>00:00:01.284</span></div>
          <div className="si-terminal__answer">
            <span>RESPONSE_001</span>
            <p>The research team approved a phased local deployment after the Aurora review. External model access remains disabled for all confidential project files.</p>
          </div>
          <div className="si-terminal__sources">
            <span>[01] APPROVAL_NOTE_24.PDF</span>
            <span>[02] PROJECT_AURORA.XLSX</span>
            <span>[03] DISCUSSION_LOG.TXT</span>
          </div>
          <div className="si-terminal__assurance"><ShieldCheck size={18} aria-hidden="true" /> ONLY AUTHORIZED KNOWLEDGE WAS SEARCHED.</div>
        </div>
      </section>

      <section className="si-final">
        <div className="si-final__brand">SI</div>
        <div className="si-final__content">
          <p>SOVEREIGN<br />INTELLIGENCE</p>
          <h2>INTELLIGENCE<br />WITHOUT<br /><span>SURRENDER.</span></h2>
          <div className="si-final__actions">
            <BrutalButton to="/signup" variant="red">ENTER SI</BrutalButton>
            <BrutalButton to="/login" variant="dark">LOGIN</BrutalButton>
          </div>
        </div>
        <footer className="si-footer">
          <span>BUILT BY SIAI</span>
          <span>SIAI / SI / SOVEREIGN INFRASTRUCTURE / 2026</span>
          <span>INTELLIGENCE_OWNED</span>
        </footer>
      </section>
    </main>
  );
}
