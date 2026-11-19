/**
 * SYSTEMIZE — Slide Deck Presentation & Pricing Engine
 * Executive, Fast, Responsive (Arabic RTL)
 */

document.addEventListener('DOMContentLoaded', () => {
  initSlideDeck();
  initPricingEngine();
});

/* ==========================================================================
   1. SLIDE DECK NAVIGATION ENGINE
   ========================================================================== */
function initSlideDeck() {
  const slides = document.querySelectorAll('.slide-panel');
  const tabs = document.querySelectorAll('.tab-btn');
  const dots = document.querySelectorAll('.deck-dot');
  const btnPrev = document.getElementById('btn-prev-slide');
  const btnNext = document.getElementById('btn-next-slide');
  const nextBtnText = document.getElementById('next-btn-text');
  const currentSlideNumEl = document.getElementById('current-slide-num');
  const progressBar = document.getElementById('deck-progress-bar');
  const advanceBtns = document.querySelectorAll('.btn-advance-slide');

  let currentSlide = 1;
  const totalSlides = slides.length || 5;

  const nextLabels = {
    1: 'التالي: الهدر القديم vs الحل ←',
    2: 'التالي: مميزات وقدرات السيستم ←',
    3: 'التالي: اختيار الباقة وحساب السعر ←',
    4: 'التالي: الشروط وسياسة الضمان ←',
    5: 'تواصل عبر واتساب للتنصيب الفوري 💬'
  };

  function goToSlide(target) {
    const slideIdx = parseInt(target, 10);
    if (isNaN(slideIdx) || slideIdx < 1 || slideIdx > totalSlides) return;

    currentSlide = slideIdx;

    // 1. Switch active slide panel
    slides.forEach(s => {
      const idx = parseInt(s.getAttribute('data-index'), 10);
      if (idx === currentSlide) {
        s.classList.add('active');
      } else {
        s.classList.remove('active');
      }
    });

    // 2. Switch active top tabs
    tabs.forEach(tab => {
      const targetIdx = parseInt(tab.getAttribute('data-target'), 10);
      if (targetIdx === currentSlide) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });

    // 3. Switch active bottom dots
    dots.forEach(dot => {
      const targetIdx = parseInt(dot.getAttribute('data-target'), 10);
      if (targetIdx === currentSlide) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });

    // 4. Update slide counter and progress bar
    if (currentSlideNumEl) currentSlideNumEl.textContent = currentSlide;
    if (progressBar) {
      const pct = (currentSlide / totalSlides) * 100;
      progressBar.style.width = `${pct}%`;
    }

    // 5. Update Previous button state
    if (btnPrev) {
      btnPrev.disabled = (currentSlide === 1);
    }

    // 6. Update Next button label & behavior
    if (nextBtnText) {
      nextBtnText.textContent = nextLabels[currentSlide] || 'التالي ←';
    }

    // Scroll to top of viewport smoothly
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Next Button Click
  if (btnNext) {
    btnNext.addEventListener('click', () => {
      if (currentSlide < totalSlides) {
        goToSlide(currentSlide + 1);
      } else {
        // If on the last slide, open WhatsApp
        const btnOrderWhatsapp = document.getElementById('btn-order-whatsapp');
        if (btnOrderWhatsapp) {
          btnOrderWhatsapp.click();
        } else {
          window.open('https://wa.me/201000000000', '_blank');
        }
      }
    });
  }

  // Prev Button Click
  if (btnPrev) {
    btnPrev.addEventListener('click', () => {
      if (currentSlide > 1) {
        goToSlide(currentSlide - 1);
      }
    });
  }

  // Top Tabs Click
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-target');
      goToSlide(target);
    });
  });

  // Bottom Dots Click
  dots.forEach(dot => {
    dot.addEventListener('click', () => {
      const target = dot.getAttribute('data-target');
      goToSlide(target);
    });
  });

  // In-Slide "Advance" Buttons Click
  advanceBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-go');
      goToSlide(target);
    });
  });

  // Keyboard Navigation (Arrow Keys)
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
      // In RTL, ArrowLeft moves forward (next)
      if (currentSlide < totalSlides) goToSlide(currentSlide + 1);
    } else if (e.key === 'ArrowRight') {
      // In RTL, ArrowRight moves backward (prev)
      if (currentSlide > 1) goToSlide(currentSlide - 1);
    }
  });

  // Mobile Touch Swipe Navigation
  let touchStartX = 0;
  let touchEndX = 0;

  window.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
  }, { passive: true });

  window.addEventListener('touchend', (e) => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
  }, { passive: true });

  function handleSwipe() {
    const diff = touchEndX - touchStartX;
    if (Math.abs(diff) > 60) {
      if (diff < 0) {
        // Swiped left -> in RTL, advance to next slide
        if (currentSlide < totalSlides) goToSlide(currentSlide + 1);
      } else {
        // Swiped right -> go to previous slide
        if (currentSlide > 1) goToSlide(currentSlide - 1);
      }
    }
  }

  // Init Slide 1
  goToSlide(1);
}

/* ==========================================================================
   2. PRICING & QUOTATION ENGINE (SLIDE 4)
   ========================================================================== */
function initPricingEngine() {
  const billingPlans = {
    monthly: {
      price: 550,
      label: '550 ج.م/شهر',
      planName: 'شهري (550 ج.م/شهر)',
      notice: '* خطة الاشتراك الشهري (550 ج.م/شهر) مع تثبيت السعر بدون أي عقود احتكارية.'
    },
    yearly: {
      price: 5500,
      label: '5,500 ج.م/سنة',
      planName: 'سنوي موصى به (5,500 ج.م/سنة — وفرت شهرين)',
      notice: '* خطة الاشتراك السنوي تشمل شهرين مجاناً (تدفع 10 شهور فقط وتعمل سنة كاملة بدون انقطاع).'
    },
    lifetime: {
      price: 11000,
      label: '11,000 ج.م للأبد',
      planName: 'مدى الحياة (11,000 ج.م — ترخيص دائم)',
      notice: '* ترخيص مدى الحياة (Lifetime): تدفع لمرة واحدة فقط وتعمل للأبد بدون أي تجديدات سنوية إطلاقاً.'
    }
  };

  const packagesConfig = {
    paper: {
      title: 'باقة «البداية الرقمية»',
      hardwareCost: 3500,
      hardwareNote: 'جهاز بصمة إصبع 500 بصمة (3,500 ج شامل التركيب)',
      licenseElId: 'pkg-paper-license',
      totalElId: 'pkg-paper-total'
    },
    switch: {
      title: 'باقة «الترقية الذكية»',
      hardwareCost: 3500,
      hardwareNote: 'مرسل واتساب + بوت تليجرام (3,500 ج)',
      licenseElId: 'pkg-switch-license',
      totalElId: 'pkg-switch-total'
    },
    vip: {
      title: 'باقة «الأتمتة الكاملة والـ VIP»',
      hardwareCost: 8500,
      hardwareNote: 'كاميرا وجه + واتساب + تليجرام (8,500 ج)',
      licenseElId: 'pkg-vip-license',
      totalElId: 'pkg-vip-total'
    }
  };

  let currentPlanKey = 'yearly';
  let selectedPkgKey = 'vip';

  // DOM Elements
  const billingButtons = document.querySelectorAll('.billing-btn');
  const billingNoticeText = document.getElementById('billing-notice-text');
  const packageCards = document.querySelectorAll('.package-card');
  const packageSelectBtns = document.querySelectorAll('.btn-package-select');
  const externalCheckboxes = document.querySelectorAll('.external-check');

  // Summary Elements
  const summaryPkgTitle = document.getElementById('summary-pkg-title');
  const summaryPlanTag = document.getElementById('summary-plan-tag');
  const summaryExtrasText = document.getElementById('summary-extras-text');
  const grandTotalDigits = document.getElementById('grand-total-digits');
  const btnOrderWhatsapp = document.getElementById('btn-order-whatsapp');

  function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
  }

  function renderPricing() {
    const plan = billingPlans[currentPlanKey];

    // 1. Update prices in each package card
    Object.keys(packagesConfig).forEach(pkgKey => {
      const pkg = packagesConfig[pkgKey];
      const licenseEl = document.getElementById(pkg.licenseElId);
      const totalEl = document.getElementById(pkg.totalElId);

      if (licenseEl) licenseEl.textContent = plan.label;

      const pkgTotal = plan.price + pkg.hardwareCost;
      if (totalEl) totalEl.textContent = formatNumber(pkgTotal);
    });

    // 2. Update visual active state on cards
    packageCards.forEach(card => {
      const cardPkgKey = card.getAttribute('data-pkg-id');
      const btn = card.querySelector('.btn-package-select');
      if (cardPkgKey === selectedPkgKey) {
        card.classList.add('selected-pkg');
        if (btn) btn.innerHTML = '<span>✓ الباقة المختارة حالياً</span>';
      } else {
        card.classList.remove('selected-pkg');
        if (btn) btn.innerHTML = `<span>اختيار ${packagesConfig[cardPkgKey].title}</span>`;
      }
    });

    // 3. Calculate selected package base cost
    const selectedPkg = packagesConfig[selectedPkgKey];
    const pkgBaseTotal = plan.price + selectedPkg.hardwareCost;

    // 4. Calculate checked external addons
    let externalSum = 0;
    const selectedAddonNames = [];

    externalCheckboxes.forEach(chk => {
      if (chk.checked) {
        const val = parseInt(chk.value, 10) || 0;
        externalSum += val;
        selectedAddonNames.push(chk.getAttribute('data-name') || 'إضافة مخصصة');
      }
    });

    // 5. Grand Total Calculation
    const grandTotal = pkgBaseTotal + externalSum;
    const formattedGrandTotal = formatNumber(grandTotal);

    // 6. Update Summary Details
    if (summaryPkgTitle) summaryPkgTitle.textContent = selectedPkg.title;
    if (summaryPlanTag) {
      summaryPlanTag.textContent = `نظام ${currentPlanKey === 'yearly' ? 'سنوي' : currentPlanKey === 'monthly' ? 'شهري' : 'مدى الحياة'}: ${plan.label}`;
    }
    if (summaryExtrasText) {
      if (selectedAddonNames.length === 0) {
        summaryExtrasText.textContent = 'بدون إضافات أجهزة خارجية إضافية';
      } else {
        summaryExtrasText.textContent = `الإضافات المختارة: + ${selectedAddonNames.join(' + ')}`;
      }
    }
    if (grandTotalDigits) grandTotalDigits.textContent = formattedGrandTotal;

    // 7. Update WhatsApp Link
    const extrasMessage = selectedAddonNames.length > 0 
      ? selectedAddonNames.map(name => `   + ${name}`).join('\n') 
      : '   لا توجد إضافات خارجية';

    const whatsappMessage = 
`مرحباً، أريد طلب تجهيز وتشغيل نظام SYSTEMIZE للجيم:
━━━━━━━━━━━━━━━━━━━━
📌 الباقة المختارة: ${selectedPkg.title}
💰 نظام ترخيص البرنامج: ${plan.planName}
📦 عتاد الباقة: ${selectedPkg.hardwareNote}
🔧 الإضافات الخارجية:
${extrasMessage}
━━━━━━━━━━━━━━━━━━━━
💵 الإجمالي الصافي المقدر: ${formattedGrandTotal} جنيه مصري

يرجى التواصل لتأكيد ميعاد المعاينة والتنصيب.`;

    const whatsappUrl = `https://wa.me/201000000000?text=${encodeURIComponent(whatsappMessage)}`;

    if (btnOrderWhatsapp) {
      btnOrderWhatsapp.onclick = () => {
        window.open(whatsappUrl, '_blank');
      };
    }
  }

  // Billing buttons event
  billingButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const planKey = btn.getAttribute('data-plan');
      if (planKey && billingPlans[planKey]) {
        currentPlanKey = planKey;
        billingButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        if (billingNoticeText) {
          billingNoticeText.textContent = billingPlans[planKey].notice;
        }

        renderPricing();
      }
    });
  });

  // Package select buttons event
  packageSelectBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const pkgKey = btn.getAttribute('data-select-pkg');
      if (pkgKey && packagesConfig[pkgKey]) {
        selectedPkgKey = pkgKey;
        renderPricing();
      }
    });
  });

  // Package card click
  packageCards.forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.btn-package-select')) return;
      const pkgKey = card.getAttribute('data-pkg-id');
      if (pkgKey && packagesConfig[pkgKey]) {
        selectedPkgKey = pkgKey;
        renderPricing();
      }
    });
  });

  // External addons checkbox change
  externalCheckboxes.forEach(chk => {
    chk.addEventListener('change', () => {
      renderPricing();
    });
  });

  // Initial render
  renderPricing();
}
