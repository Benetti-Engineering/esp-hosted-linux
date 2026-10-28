#include <stdbool.h>

#define WLAN_FC_STYPE_ASSOC_REQ     0

#define WLAN_FC_STYPE_ASSOC_RESP    1

#define WLAN_FC_STYPE_REASSOC_REQ   2

#define WLAN_FC_STYPE_REASSOC_RESP  3

#define WLAN_FC_STYPE_PROBE_REQ     4

#define WLAN_FC_STYPE_PROBE_RESP    5

#define WLAN_FC_STYPE_BEACON        8

#define WLAN_FC_STYPE_ATIM          9

#define WLAN_FC_STYPE_DISASSOC      10

#define WLAN_FC_STYPE_AUTH          11

#define WLAN_FC_STYPE_DEAUTH        12

#define WLAN_FC_STYPE_ACTION        13

#ifndef IEEE_HEADER_SIZE
#define IEEE_HEADER_SIZE            24
#endif

#define DEFAULT_SCAN_LIST_SIZE      10

#define IE_POS_ASSOC_RESP_STATUS    2

/* Frame Control byte 1 Protected Frame (IEEE80211_FCTL_PROTECTED). */
#define WLAN_FC_PROTECTED           0x40

/* Unprotected Action categories excluded by
 * _ieee80211_is_robust_mgmt_frame() in linux/ieee80211.h. */
#define WLAN_CATEGORY_PUBLIC            4
#define WLAN_CATEGORY_HT                7
#define WLAN_CATEGORY_WNM_UNPROTECTED  11
#define WLAN_CATEGORY_SELF_PROTECTED   15
#define WLAN_CATEGORY_UNPROT_DMG       20
#define WLAN_CATEGORY_VHT              21
#define WLAN_CATEGORY_S1G              22
#define WLAN_CATEGORY_VENDOR_SPECIFIC 127


static inline bool wlan_is_robust_mgmt_plain(const unsigned char *frame,
                                             unsigned int len)
{
    unsigned char stype;
    unsigned char category;

    if (!frame || len < IEEE_HEADER_SIZE)
        return false;

    stype = (frame[0] >> 4) & 0x0f;
    if (stype == WLAN_FC_STYPE_DEAUTH || stype == WLAN_FC_STYPE_DISASSOC)
        return true;
    if (stype != WLAN_FC_STYPE_ACTION || len < IEEE_HEADER_SIZE + 1)
        return false;

    category = frame[IEEE_HEADER_SIZE];
    return category != WLAN_CATEGORY_PUBLIC &&
           category != WLAN_CATEGORY_HT &&
           category != WLAN_CATEGORY_WNM_UNPROTECTED &&
           category != WLAN_CATEGORY_SELF_PROTECTED &&
           category != WLAN_CATEGORY_UNPROT_DMG &&
           category != WLAN_CATEGORY_VHT &&
           category != WLAN_CATEGORY_S1G &&
           category != WLAN_CATEGORY_VENDOR_SPECIFIC;
}
