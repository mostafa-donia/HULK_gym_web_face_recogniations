/**
 * SYSTEMIZE — 3 Tailored Packages & Quotation Engine
 * Fast, Precision-Calculated, Mobile-Optimized
 */

document.addEventListener('DOMContentLoaded', () => {
  initPricingApp();
  initBottomOnlyPill();
});

function initPricingApp() {
  // Billing plans
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

  // Packages metadata
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

  // State
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

  // Pill Elements
  const pillPkgTag = document.getElementById('pill-pkg-tag');
  const pillPriceVal = document.getElementById('pill-price-val');
  const pillWhatsappLink = document.getElementById('pill-whatsapp-link');

  function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
  }

  // Update Package Card Displays & Grand Total
  function renderAll() {
    const plan = billingPlans[currentPlanKey];

    // 1. Update each package's displayed prices
    Object.keys(packagesConfig).forEach(pkgKey => {
      const pkg = packagesConfig[pkgKey];
      const licenseEl = document.getElementById(pkg.licenseElId);
      const totalEl = document.getElementById(pkg.totalElId);

      if (licenseEl) {
        licenseEl.textContent = plan.label;
      }

      const pkgTotal = plan.price + pkg.hardwareCost;
      if (totalEl) {
        totalEl.textContent = formatNumber(pkgTotal);
      }
    });

    // 2. Update active states on package cards
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

    // 5. Final Grand Total
    const grandTotal = pkgBaseTotal + externalSum;
    const formattedGrandTotal = formatNumber(grandTotal);

    // 6. Update summary texts
    if (summaryPkgTitle) {
      summaryPkgTitle.textContent = selectedPkg.title;
    }
    if (summaryPlanTag) {
      summaryPlanTag.textContent = `نظام ${currentPlanKey === 'yearly' ? 'سنوي' : currentPlanKey === 'monthly' ? 'شهري' : 'مدى الحياة'}: ${plan.label}`;
    }
    if (summaryExtrasText) {
      if (selectedAddonNames.length === 0) {
        summaryExtrasText.textContent = 'بدون إضافات خارجية إضافية (أجهزة الطرفية)';
      } else {
        summaryExtrasText.textContent = `الإضافات المختارة: + ${selectedAddonNames.join(' + ')}`;
      }
    }
    if (grandTotalDigits) {
      grandTotalDigits.textContent = formattedGrandTotal;
    }

    // 7. Update bottom floating pill
    if (pillPkgTag) {
      pillPkgTag.textContent = selectedPkg.title;
    }
    if (pillPriceVal) {
      pillPriceVal.textContent = formattedGrandTotal;
    }

    // 8. Update WhatsApp links
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
    if (pillWhatsappLink) {
      pillWhatsappLink.href = whatsappUrl;
    }
  }

  // Event Listeners for Billing Plan Switcher
  billingButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const planKey = btn.getAttribute('data-plan');
      if (planKey && billingPlans[planKey]) {
        currentPlanKey = planKey;

        // Toggle active button class
        billingButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Update notice text
        if (billingNoticeText) {
          billingNoticeText.textContent = billingPlans[planKey].notice;
        }

        renderAll();
      }
    });
  });

  // Event Listeners for Package Selection
  packageSelectBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const pkgKey = btn.getAttribute('data-select-pkg');
      if (pkgKey && packagesConfig[pkgKey]) {
        selectedPkgKey = pkgKey;
        renderAll();

        // Smooth scroll to builder box
        const builderBox = document.getElementById('builder-box');
        if (builderBox && window.innerWidth < 860) {
          builderBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }
    });
  });

  // Make clicking anywhere on the package card select it as well
  packageCards.forEach(card => {
    card.addEventListener('click', (e) => {
      // Don't trigger if already clicked the button
      if (e.target.closest('.btn-package-select')) return;
      const pkgKey = card.getAttribute('data-pkg-id');
      if (pkgKey && packagesConfig[pkgKey]) {
        selectedPkgKey = pkgKey;
        renderAll();
      }
    });
  });

  // Event Listeners for External Addons Checkboxes
  externalCheckboxes.forEach(chk => {
    chk.addEventListener('change', () => {
      renderAll();
    });
  });

  // Initial render
  renderAll();
}

/**
 * Bottom-Only Floating Pill
 * Only appears when scrolling near the bottom of the page
 */
function initBottomOnlyPill() {
  const pill = document.getElementById('bottom-pill');
  if (!pill) return;

  function checkScrollPosition() {
    const scrollY = window.scrollY || window.pageYOffset;
    const docHeight = document.documentElement.scrollHeight;
    const winHeight = window.innerHeight;

    // Show when within 850px from bottom (near builder summary & cta)
    const distanceFromBottom = docHeight - (scrollY + winHeight);

    if (distanceFromBottom < 850) {
      pill.classList.add('is-visible');
    } else {
      pill.classList.remove('is-visible');
    }
  }

  window.addEventListener('scroll', checkScrollPosition, { passive: true });
  window.addEventListener('resize', checkScrollPosition, { passive: true });
  checkScrollPosition();
}
