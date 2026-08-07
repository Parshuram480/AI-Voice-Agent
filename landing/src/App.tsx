import { useState, useEffect, useRef } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Button,
  Card,
  CardContent,
  Typography
} from '@mui/material';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import PhoneInTalkIcon from '@mui/icons-material/PhoneInTalk';
import StorageIcon from '@mui/icons-material/Storage';
import SecurityIcon from '@mui/icons-material/Security';
import SpeedIcon from '@mui/icons-material/Speed';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SettingsInputComponentIcon from '@mui/icons-material/SettingsInputComponent';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';

// Theme configuration flag: set to false for Light Theme (default), set to true for Dark Theme
const IS_DARK_MODE = false;

const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#8b5cf6', // violet-500
    },
    background: {
      default: '#f8fafc', // slate-50
      paper: '#ffffff', // white
    },
  },
  typography: {
    fontFamily: 'Inter, system-ui, sans-serif',
  },
});

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#8b5cf6', // violet-500
    },
    background: {
      default: '#020617', // slate-950
      paper: '#0f172a', // slate-900
    },
  },
  typography: {
    fontFamily: 'Inter, system-ui, sans-serif',
  },
});

const muiTheme = IS_DARK_MODE ? darkTheme : lightTheme;

const theme = {
  bgMain: IS_DARK_MODE ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-800',
  bgCard: IS_DARK_MODE ? 'bg-slate-900/40 border-slate-800/80 shadow-xl shadow-violet-500/[0.01]' : 'bg-white border-slate-200 shadow-md shadow-slate-200/50',
  bgCardHover: IS_DARK_MODE ? 'hover:border-slate-700/80 hover:bg-slate-900' : 'hover:border-slate-300 hover:bg-slate-100/30',
  textTitle: IS_DARK_MODE ? 'text-white' : 'text-slate-900',
  textDesc: IS_DARK_MODE ? 'text-slate-400' : 'text-slate-600',
  textSub: IS_DARK_MODE ? 'text-slate-300' : 'text-slate-700',
  borderSub: IS_DARK_MODE ? 'border-slate-900' : 'border-slate-200',
  bgConsole: IS_DARK_MODE ? 'bg-slate-950 border-slate-850' : 'bg-slate-100 border-slate-200 text-slate-800',
  textAgent: IS_DARK_MODE ? 'text-violet-400' : 'text-violet-600',
  textCaller: IS_DARK_MODE ? 'text-pink-400' : 'text-pink-600',
  textStepNum: IS_DARK_MODE ? 'bg-violet-600/20 text-violet-400 border-violet-800/50' : 'bg-violet-100 text-violet-600 border-violet-200',
  bgConsoleMsg: IS_DARK_MODE ? 'bg-slate-900/60 border-slate-900' : 'bg-white border-slate-200/60',
  headerBg: IS_DARK_MODE ? 'bg-slate-950/70 border-slate-900' : 'bg-white/80 border-slate-200',
  heroVisual: IS_DARK_MODE ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200 shadow-xl',
  timelineBorder: IS_DARK_MODE ? 'border-slate-800' : 'border-slate-200',
  footerBg: IS_DARK_MODE ? 'bg-slate-950 border-slate-900' : 'bg-slate-100 border-slate-200 text-slate-700',
  footerText: IS_DARK_MODE ? 'text-slate-500' : 'text-slate-500',
  logoText: IS_DARK_MODE ? 'from-white via-slate-100 to-slate-300' : 'from-slate-900 via-slate-800 to-slate-700',
  navLink: IS_DARK_MODE ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900',
  accordionBg: IS_DARK_MODE ? 'bg-slate-900/40 border-slate-800/80' : 'bg-white border-slate-200 shadow-sm',
  accordionExpand: IS_DARK_MODE ? 'text-slate-400 font-semibold' : 'text-slate-600 font-semibold',
  dividerBorder: IS_DARK_MODE ? 'border-slate-850' : 'border-slate-200',
  glowClass: IS_DARK_MODE ? 'bg-violet-600/5' : 'bg-violet-600/[0.02]',
  heroGrad: IS_DARK_MODE
    ? 'from-violet-950/20 via-slate-950 to-slate-950'
    : 'from-violet-50/40 via-slate-50 to-slate-50',
};

// Timeline Steps for Interactive Walkthrough
const STEPS = [
  {
    number: "1",
    title: "Create Account",
    desc: "Sign up with your company name, contact details, and initial industry domain to claim your workspace.",
    image: "/images/register.png",
    figure: "Figure 2 — Registration screen",
    fallbackColor: "from-purple-900 to-indigo-900"
  },
  {
    number: "2",
    title: "Sign In",
    desc: "Log securely into your dashboard space to load your personalized industry rules and templates.",
    image: "/images/login.png",
    figure: "Figure 1 — Login screen",
    fallbackColor: "from-blue-900 to-indigo-900"
  },
  {
    number: "3",
    title: "Client Dashboard",
    desc: "Your central hub showing active connections, strategy mappings, configurations, and quick access links.",
    image: "/images/dashboard.png",
    figure: "Figure 3 — Dashboard",
    fallbackColor: "from-slate-900 to-indigo-900"
  },
  {
    number: "4",
    title: "Connect Database",
    desc: "Connect your SQLite file or PostgreSQL server. Introspect schema details securely in under a minute.",
    image: "/images/wizard-connection.png",
    figure: "Figure 4 — Database Wizard: connection setup",
    fallbackColor: "from-emerald-900 to-teal-900"
  },
  {
    number: "5",
    title: "Map Customer Table",
    desc: "Select the primary customer/leads table and map name and verification columns to build authentication rules.",
    image: "/images/wizard-mapping.png",
    figure: "Figure 5 — Database Wizard: schema mapping",
    fallbackColor: "from-violet-900 to-purple-900"
  },
  {
    number: "6",
    title: "Table & Field Selection",
    desc: "Decide which business databases and fields the AI Voice Agent is authorized to search and speak about.",
    image: "/images/wizard-selection.png",
    figure: "Figure 7 — Database Wizard: table & field selection",
    fallbackColor: "from-pink-900 to-rose-900"
  },
  {
    number: "7",
    title: "Configure Strategy & Rules",
    desc: "Confirm AI agent behaviors, target company names, and outreach goals dynamically.",
    image: "/images/wizard-outreach.png",
    figure: "Figure 6 — Database Wizard for outreach pipeline",
    fallbackColor: "from-indigo-900 to-cyan-900"
  },
  {
    number: "8",
    title: "Outbound Calling Console",
    desc: "Dial verified leads using Twilio integrations with live transcript updates and pipeline phase logs.",
    image: "/images/outbound-console.png",
    figure: "Figure 8 — Outbound call console",
    fallbackColor: "from-sky-950 to-slate-900"
  },
  {
    number: "9",
    title: "Manage Profile",
    desc: "Easily update company profile metrics, contact phone numbers, and default pipeline paths.",
    image: "/images/update-profile.png",
    figure: "Figure 9 — Update profile",
    fallbackColor: "from-slate-900 to-slate-800"
  }
];

// Industry Solutions Details
const INDUSTRIES = [
  {
    id: 0,
    name: "Sales",
    icon: <AutoAwesomeIcon />,
    tagline: "High-Converting Objection-Handling Sales Pitch Engine",
    desc: "Configure agents that make proactive outbound pitches to leads, matching brand preferences and budgets with zero caller verification frictions.",
    features: [
      "No Verification Required: Instantly dials target leads and pre-authenticates session states.",
      "Discovery Flow: Asks tailored questions about display preferences, screen sizes, and budgets.",
      "Dynamic Catalog Lookup: Queries active product tables to pitch matching items.",
      "Objection Handling: Persists up to 3 times on objections, introducing fresh incentives (promo price, specs, warranty) on each attempt.",
      "Graceful Hanging Up: Executes end_call function immediately if the lead refuses after 3 tries."
    ],
    schema: "leads (id, name, phone, max_budget) | products (id, model, brand, price, stock)"
  },
  {
    id: 1,
    name: "Healthcare",
    icon: <PhoneInTalkIcon />,
    tagline: "Strictly Verified Clinic Visit & Scheduler Assistant",
    desc: "Enforce secure patient record retrieval, check scheduled visits, and search doctor availabilities conversationally.",
    features: [
      "Strict Verification: Mandates patient name and exact date of birth (YYYY-MM-DD) before reading records.",
      "Appointment Retrieval: Fetches future scheduled appointments for verified patients.",
      "Doctor Directory Searches: Searches real-time calendars by department, doctor name, or date.",
      "Visit Updates: Handles booking, rescheduling, and cancellation requests automatically.",
      "Summary Confirmations: Dictates location details, check-in instructions, and time slots."
    ],
    schema: "patients (id, name, dob, phone_number) | appointments (id, patient_id, doctor, time, status)"
  },
  {
    id: 2,
    name: "Banking",
    icon: <SecurityIcon />,
    tagline: "Secure Identity Validation & Credit Card Services",
    desc: "Authenticate bank clients, provide balance summaries, verify pre-approved loans, and handle lost card freezes.",
    features: [
      "Card Verification: Restricts balance data access until name and last 4 card digits are verified.",
      "Account Queries: Reports savings/checking balances and statement summaries conversationally.",
      "Loan & Credit Screening: Audits credit metrics to present pre-approved loan margins.",
      "Card Freeze Tool: Instantly marks lost or stolen credit cards as blocked to prevent fraud.",
      "Fee & Interest Breakdown: Details account interest margins or transaction schedules."
    ],
    schema: "customers (id, name, credit_score) | accounts (id, balance) | offers (id, type, amount_limit)"
  },
  {
    id: 3,
    name: "Real Estate",
    icon: <StorageIcon />,
    tagline: "Proactive Buyer Qualification & Listing Scheduler",
    desc: "Filter active property directories, qualify buyer financial parameters, and book open house visits.",
    features: [
      "Lead Profiling: Qualifies prospective buyers by collecting budget ranges and pre-approval status.",
      "Advanced Listings Filters: Searches properties by location, pricing, size, and bedroom counts.",
      "Amenities Details: Communicates property facts (built year, school district, taxes, parks).",
      "Open House Booking: Connects listings to real-time calendar bookings for scheduling tours.",
      "Realtor Hand-off: Packages qualified leads and routes them directly to assigned realtors."
    ],
    schema: "inquiries (id, name, budget, location) | properties (id, price, location, bedrooms)"
  },
  {
    id: 4,
    name: "Order Tracking",
    icon: <SpeedIcon />,
    tagline: "Interactive Shipment Updates & Tracking Milestones",
    desc: "Let customers check shipping status, view carrier milestones, and update delivery directions.",
    features: [
      "Order Authentication: Asks for client name and confirmation email before fetching tracking.",
      "Carrier Status Lookup: Queries live shipping tables to state dispatch and estimated arrival dates.",
      "Transit Milestones: Provides transit locations and delays conversationally.",
      "Delivery Redirects: Updates shipping addresses if the item has not yet left the warehouse.",
      "Anomalies Logging: Automatically opens support tickets if shipments are delayed or lost."
    ],
    schema: "customers (id, name, email) | orders (id, customer_id, status, carrier, estimated_arrival)"
  },
  {
    id: 5,
    name: "Travel",
    icon: <FlightTakeoffIcon />,
    tagline: "Intelligent Travel Package Matcher & Stay Planner",
    desc: "Enable agents to pitch customized travel packages, explain membership benefits/amenities, break down trip costs, and confirm resort stay bookings.",
    features: [
      "Package Recommendation: Matches destinations, tour packages, and sightseeing itineraries based on client interest.",
      "Stay & Accommodations: Verifies hotel reservations, resort locations, room types (e.g., deluxe ocean view), and check-in dates.",
      "Benefits & Amenities: Clarifies package inclusions such as complimentary breakfast, guided excursions, and airport transfers.",
      "Charges & Fee Breakdown: Details base ticket costs, resort taxes, security deposits, and promotional discounts.",
      "Reservation Management: Instantly logs confirmed booking changes and syncs stay details to CRM databases."
    ],
    schema: "destinations (id, name, country) | packages (id, name, duration, price) | stays (id, hotel_name, room_type, price_per_night) | bookings (id, guest_name, check_in, check_out)"
  }
];

const AUDIO_FILES = [
  "/recording/Sales Agent-Happy Path (Positive).m4a",
  "/recording/Healthcare-Happy Path (Positive).m4a",
  "/recording/Banking_HappyPath_Call.mp3",
  "/recording/Realestate Sales-Happy Path (Positive).m4a",
  "/recording/order-tracking.m4a",
  "/recording/Travel_HappyPath_Call.mp3"
];

export default function App() {
  const [activeStep, setActiveStep] = useState(0);
  const [industryTab, setIndustryTab] = useState(0);
  const [imageError, setImageError] = useState<{ [key: string]: boolean }>({});

  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
      setCurrentTime(0);
      audioRef.current.load();
    }
  }, [industryTab]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().then(() => {
        setIsPlaying(true);
      }).catch(err => console.log("Audio play error: ", err));
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleAudioEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = value;
      setCurrentTime(value);
    }
  };

  const formatTime = (secs: number) => {
    if (isNaN(secs)) return "00:00";
    const minutes = Math.floor(secs / 60);
    const seconds = Math.floor(secs % 60);
    return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
  };

  useEffect(() => {
    if (IS_DARK_MODE) {
      document.documentElement.classList.add('dark-scrollbar');
    } else {
      document.documentElement.classList.remove('dark-scrollbar');
    }
  }, []);

  const handleImageError = (imgSrc: string) => {
    setImageError(prev => ({ ...prev, [imgSrc]: true }));
  };

  return (
    <ThemeProvider theme={muiTheme}>
      <div className={`font-sans ${theme.bgMain} min-h-screen transition-all selection:bg-violet-500 selection:text-white`}>
        <audio
          ref={audioRef}
          src={AUDIO_FILES[industryTab]}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleAudioEnded}
        />

        {/* 1. Header / Navbar */}
        <header className={`sticky top-0 z-50 backdrop-blur-md ${theme.headerBg} transition-all duration-300`}>
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <a
              href="#"
              onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
              className="flex items-center gap-2 sm:gap-3 hover:opacity-90 transition-opacity cursor-pointer decoration-none outline-none"
            >
              <div className="bg-gradient-to-tr from-violet-600 to-pink-500 rounded-lg p-1.5 sm:p-2 shadow-lg shadow-violet-500/20">
                <PhoneInTalkIcon className="text-white scale-90 sm:scale-105" />
              </div>
              <span className={`font-display font-extrabold text-sm sm:text-xl bg-gradient-to-r ${theme.logoText} bg-clip-text text-transparent`}>
                AI Voice Agent
              </span>
            </a>

            <nav className="hidden md:flex items-center gap-8 text-sm font-semibold">
              <a href="#features" className={`${theme.navLink} transition-colors`}>Features</a>
              <a href="#workflow" className={`${theme.navLink} transition-colors`}>Workflow</a>
              <a href="#industries" className={`${theme.navLink} transition-colors`}>Solutions</a>
              <a href="#faq" className={`${theme.navLink} transition-colors`}>FAQ</a>
            </nav>

            <div className="flex items-center gap-2 sm:gap-4">
              <Button
                component="a"
                href="http://localhost:5173/login"
                variant="text"
                className={`${theme.navLink} font-semibold capitalize tracking-wide transition-all text-xs sm:text-sm px-2 sm:px-3 min-w-0`}
              >
                Sign In
              </Button>
              <Button
                component="a"
                href="http://localhost:5173/register"
                variant="contained"
                className="cursor-pointer bg-gradient-to-r from-violet-600 to-pink-500 hover:from-violet-500 hover:to-pink-400 text-white font-bold text-xs sm:text-sm px-3 py-1.5 sm:px-5 sm:py-2 rounded-lg shadow-lg hover:shadow-violet-500/10 hover:scale-105 transition-all duration-300"
              >
                Get Started
              </Button>
            </div>
          </div>
        </header>

        {/* 2. Hero Section */}
        <section className={`relative overflow-hidden pt-20 pb-24 md:pt-28 md:pb-32 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] ${theme.heroGrad}`}>
          <div className="max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">

            {/* Hero Content */}
            <div className="lg:col-span-6 flex flex-col items-start text-left">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-violet-800/20 bg-violet-500/10 text-violet-600 text-xs font-bold uppercase tracking-wider mb-6 animate-pulse">
                <AutoAwesomeIcon className="text-xs" /> Multi-Tenant SaaS Agent Platform
              </div>

              <h1 className={`font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl ${theme.textTitle} leading-tight tracking-tight mb-6`}>
                Empower Your Business with{" "}
                <span className="bg-gradient-to-r from-violet-400 via-pink-400 to-amber-300 bg-clip-text text-transparent">
                  AI Voice Agents
                </span>
              </h1>

              <p className={`${theme.textDesc} text-lg md:text-xl leading-relaxed mb-8 max-w-xl`}>
                Automate customer calls, streamline database workflows, and deliver deeply personalized voice experiences. Instantly introspect PostgreSQL or SQLite schemas to define custom agent behaviors.
              </p>

              <div className="flex flex-wrap gap-4">
                <Button
                  component="a"
                  href="http://localhost:5173/register"
                  variant="contained"
                  className="cursor-pointer bg-gradient-to-r from-violet-600 to-pink-500 hover:from-violet-500 hover:to-pink-400 text-white font-bold px-8 py-3.5 rounded-lg shadow-xl hover:shadow-violet-500/20 transition-all duration-300"
                >
                  Get Started Free
                </Button>
                <Button
                  component="a"
                  href="#industries"
                  variant="outlined"
                  className={`border-slate-300 hover:border-slate-400 ${theme.textSub} font-semibold px-8 py-3.5 rounded-lg backdrop-blur-sm transition-all`}
                >
                  Demo
                </Button>
              </div>
            </div>

            {/* Hero Visual Mockup */}
            <div className="lg:col-span-6 relative">
              <div className="absolute -inset-0.5 bg-gradient-to-tr from-violet-500 to-pink-500 rounded-2xl opacity-20 blur-2xl"></div>
              <div className={`relative ${theme.heroVisual} rounded-2xl overflow-hidden shadow-2xl p-6`}>

                {/* Window Header Controls */}
                <div className={`flex items-center justify-between pb-4 border-b ${theme.dividerBorder} mb-6`}>
                  <div className="flex gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-rose-500 inline-block"></span>
                    <span className="w-3 h-3 rounded-full bg-amber-500 inline-block"></span>
                    <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block"></span>
                  </div>
                  <div className={`px-3 py-1 rounded ${theme.bgConsole} text-[10px] font-mono select-none`}>
                    voice-console.io/outbound
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <div className="flex justify-between items-center text-xs font-mono">
                    <span className={`${theme.textDesc}`}>Outbound Campaign</span>
                    <span className="text-emerald-500 font-bold animate-pulse">● Dialing Active</span>
                  </div>

                  {/* Voice Visualizer */}
                  <div className={`h-28 flex items-center justify-center gap-1 border-y ${theme.dividerBorder} py-4 my-2`}>
                    {[...Array(16)].map((_, i) => (
                      <span
                        key={i}
                        className="w-1.5 bg-gradient-to-t from-violet-600 to-pink-400 rounded-full transition-all duration-300 animate-pulse"
                        style={{
                          height: `${Math.max(12, Math.sin(i + activeStep) * 50 + 40)}px`,
                          animationDelay: `${i * 70}ms`
                        }}
                      ></span>
                    ))}
                  </div>

                  <div className="flex flex-col gap-2.5 text-left text-xs">
                    <p className={`font-semibold ${theme.textSub}`}>Live Conversation State:</p>
                    <div className={`p-3 rounded-lg ${theme.bgConsole} flex flex-col gap-1.5 font-mono`}>
                      <p><span className={`${theme.textAgent} font-semibold`}>Agent:</span> Hello Nilson! This is AI Voice Agent. I see you are looking to upgrade Sony entertainment system today?</p>
                      <p><span className={`${theme.textCaller} font-semibold`}>Caller:</span> Yes, I have Sony Sony budget sony SonySony sony.sony what details do we have?</p>
                    </div>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </section>

        {/* 3. Problem Statement & Solution */}
        <section id="prob-and-solution" className={`py-24 border-y ${theme.dividerBorder} ${theme.bgMain} relative`}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                Traditional Customer Service is Costly
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Manual support desks lead to expensive scaling friction and long wait times. Here is how we bridge the gap.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-20">
              {/* The Problem */}
              <div className={`${theme.bgCard} p-8 rounded-2xl text-left`}>
                <h3 className="font-display font-bold text-xl text-rose-500 mb-6 flex items-center gap-2">
                  ✕ Traditional Support Limits
                </h3>
                <ul className={`flex flex-col gap-4 ${theme.textDesc} text-sm`}>
                  <li className="flex gap-3">
                    <span className="text-rose-500 font-bold">●</span>
                    <span><strong>High Salaries Overhead:</strong> Continuous payroll expenses for agents covering peak calling hours.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-rose-500 font-bold">●</span>
                    <span><strong>Incorrect Manual Searches:</strong> Customer verification rules are often bypassed or checked inaccurately.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-rose-500 font-bold">●</span>
                    <span><strong>Disorganized Scheduling:</strong> Relies on manual booking entries that lead to double bookings.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-rose-500 font-bold">●</span>
                    <span><strong>Limited Office Hours:</strong> Restricts customer support coverage to generic business hours.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-rose-500 font-bold">●</span>
                    <span><strong>Complex Scaling:</strong> Re-training departments is slow and prone to errors.</span>
                  </li>
                </ul>
              </div>

              {/* The Solution */}
              <div className={`${theme.bgCard} p-8 rounded-2xl text-left`}>
                <h3 className="font-display font-bold text-xl text-emerald-500 mb-6 flex items-center gap-2">
                  ✓ AI Voice Agent Advantage
                </h3>
                <ul className={`flex flex-col gap-4 ${theme.textDesc} text-sm`}>
                  <li className="flex gap-3">
                    <span className="text-emerald-500 font-bold">●</span>
                    <span><strong>Instant Dynamic Verification:</strong> Auto-verify customers using name, DOB, or phone parameters.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-emerald-500 font-bold">●</span>
                    <span><strong>Live Database Lookups:</strong> Read real-time inventory counts and order tracking updates.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-emerald-500 font-bold">●</span>
                    <span><strong>24/7/365 Service:</strong> Resolve support tickets at midnight or holidays with zero overhead.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-emerald-500 font-bold">●</span>
                    <span><strong>Pre-authenticated Sales Flow:</strong> Instantly pitch catalog products to outbound leads.</span>
                  </li>
                  <li className="flex gap-3">
                    <span className="text-emerald-500 font-bold">●</span>
                    <span><strong>Automated System Hand-off:</strong> Connect to Twilio to make real call streams seamlessly.</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Features Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card className={`${theme.bgCard} ${theme.bgCardHover} rounded-xl transition-all duration-300 border`}>
                <CardContent className="p-6 flex flex-col items-start text-left">
                  <div className="bg-violet-500/10 p-3 rounded-lg text-violet-500 mb-4"><StorageIcon /></div>
                  <h4 className={`font-display font-bold text-base ${theme.textTitle} mb-2`}>No-Code DB Setup</h4>
                  <p className={`${theme.textDesc} text-xs leading-relaxed`}>Securely upload SQLite files or input PostgreSQL/MSSQL credentials to introspect schemas instantly.</p>
                </CardContent>
              </Card>

              <Card className={`${theme.bgCard} ${theme.bgCardHover} rounded-xl transition-all duration-300 border`}>
                <CardContent className="p-6 flex flex-col items-start text-left">
                  <div className="bg-pink-500/10 p-3 rounded-lg text-pink-500 mb-4"><SettingsInputComponentIcon /></div>
                  <h4 className={`font-display font-bold text-base ${theme.textTitle} mb-2`}>Easy Configuration</h4>
                  <p className={`${theme.textDesc} text-xs leading-relaxed`}>Map primary customer tables, choose columns the AI is allowed to speak about, and configure strategy rules.</p>
                </CardContent>
              </Card>

              <Card className={`${theme.bgCard} ${theme.bgCardHover} rounded-xl transition-all duration-300 border`}>
                <CardContent className="p-6 flex flex-col items-start text-left">
                  <div className="bg-emerald-500/10 p-3 rounded-lg text-emerald-500 mb-4"><SecurityIcon /></div>
                  <h4 className={`font-display font-bold text-base ${theme.textTitle} mb-2`}>Secure Authentication</h4>
                  <p className={`${theme.textDesc} text-xs leading-relaxed`}>Sensitive passwords and connection strings are encrypted. Supports standard SSL database rules.</p>
                </CardContent>
              </Card>

              <Card className={`${theme.bgCard} ${theme.bgCardHover} rounded-xl transition-all duration-300 border`}>
                <CardContent className="p-6 flex flex-col items-start text-left">
                  <div className="bg-amber-500/10 p-3 rounded-lg text-amber-500 mb-4"><PhoneInTalkIcon /></div>
                  <h4 className={`font-display font-bold text-base ${theme.textTitle} mb-2`}>Multi-Domain Support</h4>
                  <p className={`${theme.textDesc} text-xs leading-relaxed`}>Select pre-configured pipelines for Sales, Banking, Healthcare, Real Estate, or Order Tracking.</p>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>

        {/* 9. Key Features */}
        <section id="features" className={`py-24 ${theme.bgMain} border-b ${theme.dividerBorder} relative`}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold text-violet-500 uppercase tracking-widest block mb-2">Core Product Capabilities</span>
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                Key Features
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                A comprehensive toolset engineered to deploy conversational voice automation securely.
              </p>
            </div>

            <div className="flex flex-col gap-24">

              {/* Feature 1: Multi-Domain Support (Left Content, Right Image) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 text-left flex flex-col items-start">
                  <span className="p-3 rounded-xl bg-violet-500/10 text-violet-500 text-sm flex mb-4"><PhoneInTalkIcon /></span>
                  <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                    Multi-Domain Support
                  </h3>
                  <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                    Deploy specialized calling strategies tailored directly to your customer workflows out-of-the-box:
                  </p>
                  <ul className={`flex flex-col gap-3 text-xs ${theme.textDesc}`}>
                    <li className="flex gap-2">
                      <span className="text-violet-500">✓</span> <span><strong>Sales:</strong> Pitches products, budget discovery matching, and objection handling.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-violet-500">✓</span> <span><strong>Banking:</strong> Secure balance checks, loan status, and stolen card blocks.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-violet-500">✓</span> <span><strong>Healthcare:</strong> DOB verification, patient profiles, and booking details.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-violet-500">✓</span> <span><strong>Real Estate:</strong> Property listings search, buyer qualification, and tours.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-violet-500">✓</span> <span><strong>Order Tracking:</strong> Tracking status checkups and delivery redirects.</span>
                    </li>
                  </ul>
                </div>
                <div className={`lg:col-span-6 group relative rounded-2xl overflow-hidden border ${theme.dividerBorder} ${theme.bgCard} p-2 hover:border-slate-400 transition-all duration-300`}>
                  <div className="relative aspect-video w-full rounded-xl overflow-hidden">
                    <div className="absolute inset-0 bg-slate-950/10 z-10"></div>
                    <img
                      src="images/key-features/multi-domain.png"
                      alt="Multi-Domain Support"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                </div>
              </div>

              {/* Feature 2: Database Integration (Left Image, Right Content) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 lg:order-2 text-left flex flex-col items-start">
                  <span className="p-3 rounded-xl bg-pink-500/10 text-pink-500 text-sm flex mb-4"><StorageIcon /></span>
                  <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                    Database Integration
                  </h3>
                  <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                    Link your product catalogs and customer directories securely with complete multi-database support:
                  </p>
                  <ul className={`flex flex-col gap-3 text-xs ${theme.textDesc}`}>
                    <li className="flex gap-2">
                      <span className="text-pink-500">✓</span> <span><strong>SQLite:</strong> Upload local .db or .sqlite files directly.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-pink-500">✓</span> <span><strong>PostgreSQL:</strong> Full support for cloud databases.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-pink-500">✓</span> <span><strong>MSSQL:</strong> Enterprise server integration capability.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-pink-500">✓</span> <span><strong>MySQL:</strong> Relational database table parsing.</span>
                    </li>
                  </ul>
                </div>
                <div className={`lg:col-span-6 lg:order-1 group relative rounded-2xl overflow-hidden border ${theme.dividerBorder} ${theme.bgCard} p-2 hover:border-slate-400 transition-all duration-300`}>
                  <div className="relative aspect-video w-full rounded-xl overflow-hidden">
                    <div className="absolute inset-0 bg-slate-950/10 z-10"></div>
                    <img
                      src="images/key-features/db.png"
                      alt="Database Integration"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                </div>
              </div>

              {/* Feature 3: Secure Authentication (Left Content, Right Image) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 text-left flex flex-col items-start">
                  <span className="p-3 rounded-xl bg-emerald-500/10 text-emerald-500 text-sm flex mb-4"><SecurityIcon /></span>
                  <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                    Secure Authentication
                  </h3>
                  <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                    Ensure strict caller validation protocols, protecting account metrics and private fields:
                  </p>
                  <ul className={`flex flex-col gap-3 text-xs ${theme.textDesc}`}>
                    <li className="flex gap-2">
                      <span className="text-emerald-500">✓</span> <span><strong>Secure Tenant Login:</strong> Fully isolated dashboards for each business client.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-500">✓</span> <span><strong>OTP Validation:</strong> Send verification codes dynamically to verify transactions.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-emerald-500">✓</span> <span><strong>Role Access Control:</strong> Configure specific read/write access margins to agents.</span>
                    </li>
                  </ul>
                </div>
                <div className={`lg:col-span-6 group relative rounded-2xl overflow-hidden border ${theme.dividerBorder} ${theme.bgCard} p-2 hover:border-slate-400 transition-all duration-300`}>
                  <div className="relative aspect-video w-full rounded-xl overflow-hidden">
                    <div className="absolute inset-0 bg-slate-950/10 z-10"></div>
                    <img
                      src="images/key-features/secure-auth.png"
                      alt="Secure Authentication"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                </div>
              </div>

              {/* Feature 4: Multi-language Support (Left Image, Right Content) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 lg:order-2 text-left flex flex-col items-start">
                  <span className="p-3 rounded-xl bg-amber-500/10 text-amber-500 text-sm flex mb-4"><AutoAwesomeIcon /></span>
                  <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                    Multi-language Support
                  </h3>
                  <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                    Build conversational pipelines that match standard speaking rates globally:
                  </p>
                  <ul className={`flex flex-col gap-3 text-xs ${theme.textDesc}`}>
                    <li className="flex gap-2">
                      <span className="text-amber-500">✓</span> <span><strong>English Support:</strong> Conversational clarity mapping regional accents and phrases.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="text-amber-500">✓</span> <span><strong>Hindi Support (हिंदी):</strong> Native conversational fluency, supporting both pure Hindi and bilingual (Hinglish) dialogue parameters.</span>
                    </li>
                  </ul>
                </div>
                <div className={`lg:col-span-6 lg:order-1 group relative rounded-2xl overflow-hidden border ${theme.dividerBorder} ${theme.bgCard} p-2 hover:border-slate-400 transition-all duration-300`}>
                  <div className="relative aspect-video w-full rounded-xl overflow-hidden">
                    <div className="absolute inset-0 bg-slate-950/10 z-10"></div>
                    <img
                      src="images/key-features/multi-language.png"
                      alt="Multi-language Support"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                </div>
              </div>

              {/* Feature 5: Easy Configuration (Left Content, Right Image) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                <div className="lg:col-span-6 text-left flex flex-col items-start">
                  <span className="p-3 rounded-xl bg-sky-500/10 text-sky-500 text-sm flex mb-4"><SettingsInputComponentIcon /></span>
                  <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                    Easy Configuration
                  </h3>
                  <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                    Build, test, and save database mappings with our highly visual setups:
                  </p>
                  <ul className={`flex flex-col gap-3 text-xs ${theme.textDesc}`}>
                    <li className="flex gap-2">
                      <span className="text-sky-500">✓</span> <span><strong>No Coding Required:</strong> Complete schema mapping and strategy definition visually in minutes.</span>
                    </li>
                  </ul>
                </div>
                <div className={`lg:col-span-6 group relative rounded-2xl overflow-hidden border ${theme.dividerBorder} ${theme.bgCard} p-2 hover:border-slate-400 transition-all duration-300`}>
                  <div className="relative aspect-video w-full rounded-xl overflow-hidden">
                    <div className="absolute inset-0 bg-slate-950/10 z-10"></div>
                    <img
                      src="images/key-features/easy-config.png"
                      alt="Easy Configuration"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* 10. How It Works Timeline */}
        <section className={`py-24 ${theme.bgMain} border-b ${theme.dividerBorder} relative`}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold text-violet-500 uppercase tracking-widest block mb-2">Step-by-Step Setup Guide</span>
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                How It Works
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Follow this timeline to configure and deploy your voice assistant campaign.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6 relative">
              {/* Step 1 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  01
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Create Account</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Register your company workspace on the platform.</p>
              </div>

              {/* Step 2 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  02
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Choose Industry</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Select pre-configured domain strategies like Sales or Healthcare.</p>
              </div>

              {/* Step 3 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  03
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Connect Database</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Upload SQLite files or connect your PostgreSQL server.</p>
              </div>

              {/* Step 4 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  04
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Map Customer Table</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Define verification rules and primary search keys.</p>
              </div>

              {/* Step 5 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  05
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Configure AI Rules</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Detail allowed fields, variables, and agent traits.</p>
              </div>

              {/* Step 6 */}
              <div className={`${theme.bgCard} rounded-xl p-6 flex flex-col items-center text-center hover:border-slate-400 transition-all duration-300 border relative`}>
                <div className={`w-10 h-10 rounded-full ${theme.textStepNum} flex items-center justify-center font-display font-extrabold text-sm mb-4`}>
                  06
                </div>
                <h4 className={`font-display font-bold text-sm ${theme.textTitle} mb-2`}>Start Calling</h4>
                <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>Place outbound Twilio phone calls or run browser tests.</p>
              </div>
            </div>
          </div>
        </section>

        {/* 4. Interactive Workflow Walkthrough */}
        <section id="workflow" className={`py-24 ${theme.bgMain} border-b ${theme.dividerBorder}`}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                End-to-End Platform Walkthrough
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Explore how the platform guides you from creating your account to launching real phone calls.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">

              {/* Steps Timeline (Left: 5cols) */}
              <div className="lg:col-span-5 flex flex-col gap-4 text-left relative max-h-[520px] overflow-y-auto pr-3">
                <div className={`absolute left-[27px] top-6 bottom-6 w-0.5 border-l-2 border-dashed ${theme.timelineBorder} -z-10`}></div>

                {STEPS.map((step, idx) => {
                  const isActive = activeStep === idx;
                  return (
                    <button
                      key={idx}
                      onClick={() => setActiveStep(idx)}
                      className={`flex gap-5 p-4 rounded-xl text-left transition-all duration-300 cursor-pointer ${isActive
                        ? `${theme.bgCard} border border-slate-350 scale-102`
                        : 'hover:bg-slate-100/40 border border-transparent'
                        }`}
                    >
                      <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center font-bold text-xs transition-all ${isActive
                        ? 'bg-violet-600 text-white shadow shadow-violet-600/35'
                        : `${theme.bgConsole} border ${theme.dividerBorder}`
                        }`}>
                        {step.number}
                      </div>
                      <div>
                        <h4 className={`font-display font-bold text-sm ${isActive ? 'text-violet-500' : theme.textTitle} mb-1 transition-colors`}>
                          {step.title}
                        </h4>
                        <p className={`${theme.textDesc} text-[10px] leading-relaxed`}>
                          {step.desc}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Visual Screen Mockup Frame (Right: 7cols) */}
              <div className="lg:col-span-7 relative">
                <div className="absolute -inset-0.5 bg-gradient-to-tr from-violet-500 to-pink-500 rounded-2xl opacity-15 blur-xl"></div>
                <div className={`relative ${theme.bgCard} rounded-2xl p-5 border shadow-2xl`}>

                  {/* Header Window Bar */}
                  <div className={`flex items-center justify-between pb-3 border-b ${theme.dividerBorder} mb-4`}>
                    <div className="flex gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
                    </div>
                    <div className={`px-2 py-0.5 rounded ${theme.bgConsole} text-[9px] font-mono select-none font-bold`}>
                      {STEPS[activeStep].title}
                    </div>
                  </div>

                  {/* Visual Content Display */}
                  <div className={`w-full relative aspect-video rounded-xl overflow-hidden ${theme.bgConsole} flex items-center justify-center border group`}>
                    {imageError[STEPS[activeStep].image] ? (
                      /* Fallback Graphic */
                      <div className={`absolute inset-0 bg-gradient-to-tr ${STEPS[activeStep].fallbackColor} flex flex-col items-center justify-center p-8 text-center`}>
                        <AutoAwesomeIcon className="text-white/40 text-4xl mb-3 animate-pulse" />
                        <h4 className="font-display font-bold text-white text-base mb-2">{STEPS[activeStep].title}</h4>
                        <p className="text-white/70 text-xs max-w-sm">{STEPS[activeStep].desc}</p>
                        <span className="mt-4 text-[9px] font-mono text-white/50 bg-black/30 px-2 py-1 rounded">Asset: {STEPS[activeStep].image}</span>
                      </div>
                    ) : (
                      /* Real Image */
                      <img
                        src={STEPS[activeStep].image}
                        alt={STEPS[activeStep].title}
                        onError={() => handleImageError(STEPS[activeStep].image)}
                        className="w-full h-full object-contain group-hover:scale-101 transition-transform duration-500"
                      />
                    )}
                  </div>

                  <p className={`text-center font-mono ${theme.textDesc} text-xs mt-3 select-none`}>
                    {STEPS[activeStep].figure}
                  </p>

                </div>
              </div>

            </div>
          </div>
        </section>

        {/* 5. Industry Solutions Tabs */}
        <section id="industries" className={`py-24 ${theme.bgMain} border-b ${theme.dividerBorder} relative`}>
          <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] ${theme.glowClass} rounded-full blur-3xl pointer-events-none`}></div>
          <div className="max-w-7xl mx-auto px-6 relative">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold text-violet-500 uppercase tracking-widest block mb-2">Pre-built Calling Campaigns</span>
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                Configured Industry Solutions
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Out-of-the-box conversational state flows mapped directly to database schemas.
              </p>
            </div>

            <div className="flex flex-col items-center">
              {/* Custom Interactive Pill Tabs */}
              <div className="flex flex-wrap justify-center gap-2 sm:gap-3 mb-12 w-full max-w-5xl px-4">
                {INDUSTRIES.map((ind, idx) => (
                  <button
                    key={idx}
                    onClick={() => setIndustryTab(idx)}
                    className={`flex items-center gap-1.5 sm:gap-2 px-3.5 sm:px-5 py-2 sm:py-3 rounded-full font-display font-bold text-xs sm:text-sm cursor-pointer transition-all duration-300 ${industryTab === idx
                      ? 'bg-gradient-to-r from-violet-600 to-pink-500 text-white shadow-lg shadow-violet-500/20 scale-105'
                      : `${theme.bgCard} ${theme.bgCardHover} text-slate-500 hover:text-slate-900 border`
                      }`}
                  >
                    <span className="scale-90 flex items-center">{ind.icon}</span>
                    <span>{ind.name}</span>
                  </button>
                ))}
              </div>

              {/* Tab Details Card (Alternating/Split Grid) */}
              <div className="w-full max-w-5xl">
                <div className={`${theme.bgCard} rounded-3xl p-8 text-left grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch border`}>

                  {/* Content Panel (Left: 7cols) */}
                  <div className="lg:col-span-7 flex flex-col justify-between items-start">
                    <div>
                      <span className="text-xs font-bold text-violet-500 uppercase tracking-widest block mb-2">
                        {INDUSTRIES[industryTab].tagline}
                      </span>
                      <h3 className={`font-display font-extrabold text-2xl sm:text-3xl ${theme.textTitle} mb-4`}>
                        {INDUSTRIES[industryTab].name} Solutions Flow
                      </h3>
                      <p className={`${theme.textDesc} text-sm leading-relaxed mb-6`}>
                        {INDUSTRIES[industryTab].desc}
                      </p>

                      <h4 className={`font-bold text-xs ${theme.textSub} uppercase tracking-wider mb-3`}>Key Rules & Functions:</h4>
                      <ul className={`flex flex-col gap-2.5 text-xs ${theme.textDesc} mb-6`}>
                        {INDUSTRIES[industryTab].features.map((feat, fidx) => (
                          <li key={fidx} className="flex gap-2">
                            <span className="text-violet-500 font-bold">✔</span>
                            <span>{feat}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="flex gap-4">
                      <Button
                        component="a"
                        href="http://localhost:5173/login"
                        variant="contained"
                        className="cursor-pointer capitalize bg-gradient-to-r from-violet-600 to-pink-500 text-white font-bold px-6 py-2.5 rounded-xl hover:opacity-90 transition-opacity shadow-lg shadow-violet-600/25 border-0 text-xs"
                      >
                        Launch Campaign
                      </Button>
                    </div>
                  </div>

                  {/* Console Simulation Panel (Right: 5cols) */}
                  <div className="lg:col-span-5 flex flex-col justify-center">
                    <div className={`flex flex-col gap-5 font-mono text-xs text-left ${theme.bgConsole} p-6 rounded-2xl border shadow-inner h-full justify-between`}>
                      <div>
                        {/* Header Status Bar */}
                        <div className={`flex justify-between items-center border-b ${theme.dividerBorder} pb-3 mb-4`}>
                          <span className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">Call Console</span>
                          {industryTab === 0 && <span className="text-emerald-500 font-bold animate-pulse text-[10px]">● Outbound Dialing</span>}
                          {industryTab === 1 && <span className="text-violet-500 font-bold text-[10px]">✓ Secure Verification</span>}
                          {industryTab === 2 && <span className="text-rose-500 font-bold animate-pulse text-[10px]">🔒 High Security</span>}
                          {industryTab === 3 && <span className="text-amber-500 font-bold text-[10px]">❖ Lead Profile</span>}
                          {industryTab === 4 && <span className="text-sky-500 font-bold text-[10px]">🚚 FedEx Tracking</span>}
                          {industryTab === 5 && <span className="text-indigo-500 font-bold text-[10px]">✈ Airline Check-In</span>}
                        </div>

                        {/* Interactive Voice Wave Visualizer */}
                        <div className="h-32 flex items-center justify-center gap-1 border-y border-slate-200/10 dark:border-slate-800 py-6 my-4 w-full bg-slate-950/5 dark:bg-slate-950/20 rounded-lg">
                          {[...Array(20)].map((_, i) => (
                            <span
                              key={i}
                              className={`w-1 rounded-full transition-all duration-300 ${
                                isPlaying
                                  ? 'bg-gradient-to-t from-violet-600 to-pink-500 animate-pulse'
                                  : 'bg-slate-300 dark:bg-slate-800'
                              }`}
                              style={{
                                height: isPlaying
                                  ? `${Math.max(12, Math.sin(i * 0.7 + currentTime * 6) * 50 + 40)}px`
                                  : '12px',
                                animationDelay: `${i * 35}ms`
                              }}
                            ></span>
                          ))}
                        </div>

                        {/* Custom Audio Controller */}
                        <div className="flex flex-col gap-3 mt-4">
                          <div className="flex items-center justify-between text-[10px] text-slate-400 font-sans">
                            <span className="font-semibold uppercase tracking-wider">Play Call Recording</span>
                            <span className="font-mono">{formatTime(currentTime)} / {formatTime(duration)}</span>
                          </div>

                          <div className="flex items-center gap-3">
                            <button
                              onClick={togglePlay}
                              className="w-10 h-10 rounded-full bg-gradient-to-r from-violet-600 to-pink-500 hover:scale-105 hover:shadow-lg text-white flex items-center justify-center cursor-pointer shadow transition-all flex-shrink-0"
                            >
                              {isPlaying ? (
                                <span className="text-[10px] font-bold">❚❚</span>
                              ) : (
                                <span className="text-[14px] ml-0.5">▶</span>
                              )}
                            </button>

                            <input
                              type="range"
                              min="0"
                              max={duration || 100}
                              value={currentTime}
                              onChange={handleSeek}
                              className="w-full h-1 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-violet-600 outline-none"
                            />
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 border-t border-slate-900/10 dark:border-slate-900/40 pt-3 text-[9px] text-slate-500 flex justify-between font-sans">
                        <span>Console Active</span>
                        <span>Agent Status: Ready</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 2.7 Trusted Statistics Section */}
        <section className={`py-24 ${theme.bgMain} border-t ${theme.dividerBorder} relative animate-fade-in`}>
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold text-violet-500 uppercase tracking-widest block mb-2">Performance Standards</span>
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                Trusted Statistics
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Our infrastructure is optimized for industry-leading latency, reliability, and precision at enterprise scales.
              </p>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">

              {/* Stat 1 */}
              <div className={`${theme.bgCard} rounded-2xl p-6 md:p-8 hover:bg-slate-900/40 hover:border-slate-800 transition-all duration-300 border`}>
                <div className="font-display font-extrabold text-3xl md:text-5xl bg-gradient-to-r from-violet-400 to-pink-500 bg-clip-text text-transparent mb-2 animate-pulse">
                  90%
                </div>
                <div className={`text-xs md:text-sm font-semibold ${theme.textSub}`}>Accuracy</div>
                <div className="text-[10px] text-slate-500 mt-1">High fidelity speech mapping</div>
              </div>

              {/* Stat 2 */}
              <div className={`${theme.bgCard} rounded-2xl p-6 md:p-8 hover:bg-slate-900/40 hover:border-slate-800 transition-all duration-300 border`}>
                <div className="font-display font-extrabold text-3xl md:text-5xl bg-gradient-to-r from-pink-400 to-rose-500 bg-clip-text text-transparent mb-2 animate-pulse">
                  &lt; 1.5s
                </div>
                <div className={`text-xs md:text-sm font-semibold ${theme.textSub}`}>Latency</div>
                <div className="text-[10px] text-slate-500 mt-1">Instant conversational response</div>
              </div>

              {/* Stat 3 */}
              <div className={`${theme.bgCard} rounded-2xl p-6 md:p-8 hover:bg-slate-900/40 hover:border-slate-800 transition-all duration-300 border`}>
                <div className="font-display font-extrabold text-3xl md:text-5xl bg-gradient-to-r from-rose-400 to-amber-500 bg-clip-text text-transparent mb-2 animate-pulse">
                  99.9%
                </div>
                <div className={`text-xs md:text-sm font-semibold ${theme.textSub}`}>Uptime</div>
                <div className="text-[10px] text-slate-500 mt-1">Enterprise SLA guarantees</div>
              </div>

              {/* Stat 4 */}
              <div className={`${theme.bgCard} rounded-2xl p-6 md:p-8 hover:bg-slate-900/40 hover:border-slate-800 transition-all duration-300 border`}>
                <div className="font-display font-extrabold text-3xl md:text-5xl bg-gradient-to-r from-violet-400 to-sky-500 bg-clip-text text-transparent mb-2 animate-pulse">
                  24/7
                </div>
                <div className={`text-xs md:text-sm font-semibold ${theme.textSub}`}>AI Calling</div>
                <div className="text-[10px] text-slate-500 mt-1">Continuous customer outreach</div>
              </div>

            </div>
          </div>
        </section>

        {/* 6. Frequently Asked Questions (FAQ) */}
        <section id="faq" className={`py-24 ${theme.bgMain} border-b ${theme.dividerBorder}`}>
          <div className="max-w-4xl mx-auto px-6">
            <div className="text-center mb-16">
              <h2 className={`font-display font-extrabold text-3xl sm:text-4xl ${theme.textTitle} mb-4`}>
                Frequently Asked Questions
              </h2>
              <p className={`${theme.textDesc} text-lg`}>
                Got questions about setup, databases, or Twilio configurations? We have answers.
              </p>
            </div>

            <div className="flex flex-col gap-4">
              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Can I connect my own database?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. You can input cloud credentials for PostgreSQL, or upload SQLite databases directly in your browser. All connections are processed securely.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Which databases are supported?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    We natively support PostgreSQL, SQLite, Microsoft SQL Server (MSSQL), and MySQL. Schema introspection happens instantly upon connection.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Can I customize the AI prompts?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. You can write custom rules, define permitted tables and columns the AI is allowed to speak about, and set specific prompt guidelines for customer objections.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Can I use my own Twilio account?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. The platform provides a native integration step where you can input your Twilio Account SID, Auth Token, and phone numbers to route call streams.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Does it support multiple businesses?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. The platform is designed as a multi-tenant SaaS. Organizations register isolated workspaces that manage separate database connections, rules, and campaigns.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Can I upload SQLite databases?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. The database integration step allows you to drag and drop or browse for local SQLite database files. Once uploaded, the platform instantly inspects the tables, columns, and relations to generate tools for the agent.
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion className={`${theme.accordionBg} rounded-xl text-left before:hidden shadow-none transition-all border`}>
                <AccordionSummary expandIcon={<ExpandMoreIcon className={`${theme.accordionExpand}`} />}>
                  <Typography className={`font-bold text-sm ${theme.textTitle}`}>Is my data secure?</Typography>
                </AccordionSummary>
                <AccordionDetails className={`border-t ${theme.dividerBorder}`}>
                  <Typography className={`text-xs ${theme.textDesc} leading-relaxed`}>
                    Yes. Sensitive credentials and database connection strings are encrypted before being stored. Furthermore, the platform isolates tenant databases and supports secure SSL connections to postgres servers to prevent data leaks.
                  </Typography>
                </AccordionDetails>
              </Accordion>
            </div>
          </div>
        </section>

        {/* 7. Footer */}
        <footer className={`${theme.footerBg} py-12 border-t transition-all`}>
          <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
            <a
              href="#"
              onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
              className="flex items-center gap-3 hover:opacity-90 transition-opacity cursor-pointer decoration-none outline-none"
            >
              <div className="bg-gradient-to-tr from-violet-600 to-pink-500 rounded-lg p-1.5 text-white">
                <PhoneInTalkIcon className="scale-90" />
              </div>
              <span className={`font-display font-bold ${theme.textSub}`}>AI Voice Agent</span>
            </a>

            <p className={`text-xs ${theme.footerText} font-semibold select-none`}>
              &copy; {new Date().getFullYear()} Voice Agent SaaS Platform. All rights reserved.
            </p>

            {/* <div className={`flex gap-4 text-xs font-semibold ${theme.footerText}`}>
            <a href="#features" className="hover:text-violet-500 transition-colors">Privacy Policy</a>
            <a href="#features" className="hover:text-violet-500 transition-colors">Terms of Service</a>
          </div> */}
          </div>
        </footer>

      </div>
    </ThemeProvider>
  );
}
