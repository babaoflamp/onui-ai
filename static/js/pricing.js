/**
 * Pricing Page JavaScript
 * Handles pricing toggle, FAQ interactions, and plan selection
 */

(function () {
  'use strict';

  // ===========================
  // Pricing Toggle (월간/연간)
  // ===========================

  const pricingToggle = document.getElementById('pricing-toggle');
  const toggleIndicator = document.getElementById('toggle-indicator');
  const monthlyLabels = document.querySelectorAll('.monthly-price, .monthly-period');
  const annualLabels = document.querySelectorAll('.annual-price, .annual-period');
  const annualSavings = document.querySelectorAll('.annual-savings');

  let isAnnual = false;

  if (pricingToggle) {
    pricingToggle.addEventListener('click', function () {
      isAnnual = !isAnnual;
      pricingToggle.setAttribute('aria-checked', isAnnual);

      // Toggle visibility
      if (isAnnual) {
        monthlyLabels.forEach(el => {
          el.classList.add('hidden');
        });
        annualLabels.forEach(el => {
          el.classList.remove('hidden');
        });
        annualSavings.forEach(el => {
          el.classList.remove('hidden');
        });
      } else {
        monthlyLabels.forEach(el => {
          el.classList.remove('hidden');
        });
        annualLabels.forEach(el => {
          el.classList.add('hidden');
        });
        annualSavings.forEach(el => {
          el.classList.add('hidden');
        });
      }
    });
  }

  // ===========================
  // FAQ Toggle
  // ===========================

  window.toggleFAQ = function (button) {
    const answer = button.nextElementSibling;
    const isOpen = answer.classList.contains('show');

    // Close all FAQs
    document.querySelectorAll('.faq-answer').forEach(faq => {
      faq.classList.remove('show');
    });
    document.querySelectorAll('.faq-question').forEach(btn => {
      btn.classList.remove('active');
      const icon = btn.querySelector('span');
      if (icon) icon.textContent = '+';
    });

    // Toggle current FAQ
    if (!isOpen) {
      answer.classList.add('show');
      button.classList.add('active');
      const icon = button.querySelector('span');
      if (icon) icon.textContent = '−';
    }
  };

  // ===========================
  // Plan Selection Tracking
  // ===========================

  const planButtons = document.querySelectorAll('.pricing-card button');

  planButtons.forEach(button => {
    button.addEventListener('click', function (e) {
      const card = this.closest('.pricing-card');
      const planName = card.querySelector('h3').textContent;
      const planPrice = card.querySelector('.text-4xl').textContent;

      console.log('Plan selected:', {
        plan: planName,
        price: planPrice,
        isAnnual: isAnnual
      });

      // TODO: Integrate with backend signup/payment flow
      // For now, redirect to signup/login page
      // e.preventDefault();
      // alert(`${planName} 플랜을 선택하셨습니다.\n가격: ${planPrice}\n결제 주기: ${isAnnual ? '연간' : '월간'}`);
    });
  });

  // ===========================
  // Smooth Scroll to Sections
  // ===========================

  const anchors = document.querySelectorAll('a[href^="#"]');

  anchors.forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href !== '#') {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      }
    });
  });

  // ===========================
  // Price Calculation Helper
  // ===========================

  function calculateSavings(monthlyPrice, annualPrice) {
    const monthlyTotal = monthlyPrice * 12;
    const savings = monthlyTotal - annualPrice;
    const savingsPercent = Math.round((savings / monthlyTotal) * 100);

    return {
      savings: savings,
      savingsPercent: savingsPercent,
      monthlyEquivalent: Math.round(annualPrice / 12)
    };
  }

  // Example usage for Standard plan
  const standardMonthly = 9900;
  const standardAnnual = 99000;
  const standardSavings = calculateSavings(standardMonthly, standardAnnual);

  console.log('Standard Plan Savings:', standardSavings);
  // Output: { savings: 19800, savingsPercent: 17, monthlyEquivalent: 8250 }

  // ===========================
  // Discount Code Input (Future)
  // ===========================

  // This can be expanded when discount code functionality is added
  window.applyDiscountCode = function (code) {
    console.log('Applying discount code:', code);
    // TODO: Validate discount code with backend
    return false;
  };

  // ===========================
  // Analytics Tracking (Optional)
  // ===========================

  // Track page view
  console.log('Pricing page loaded');

  // Track pricing toggle
  if (pricingToggle) {
    pricingToggle.addEventListener('click', function () {
      console.log('Pricing toggle:', isAnnual ? 'Annual' : 'Monthly');
    });
  }

  // Track FAQ interactions
  document.querySelectorAll('.faq-question').forEach(button => {
    button.addEventListener('click', function () {
      const question = this.querySelector('h3').textContent;
      console.log('FAQ clicked:', question);
    });
  });

  // ===========================
  // Mobile Responsiveness Check
  // ===========================

  function checkMobileView() {
    const isMobile = window.innerWidth < 768;
    console.log('Mobile view:', isMobile);
    return isMobile;
  }

  window.addEventListener('resize', function () {
    checkMobileView();
  });

  // Initial check
  checkMobileView();

})();
